"""Distill Claude Opus 5.5 into short SFT targets for one training round.

This runs on the machine that has ``ANTHROPIC_API_KEY``. It does not run
inside the checkout that has no key. Unit tests inject ``create_fn`` and
never open a socket.

Only train pages are sent. Dev pages and the frozen test set are refused.
The teacher is ``claude-opus-5-5`` and nothing else. Spend is cumulative in
``~/.guardgym/anthropic_teacher_ledger.json`` and stops at ``--max-usd``
(default $50). A cache hit costs nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEACHER_MODEL = "claude-opus-5-5"
DEFAULT_MAX_USD = "50"
MAX_OUTPUT_TOKENS = 640
MAX_TARGET_TOKENS = 120
MAX_WORKERS = 8
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})
RETRY_ATTEMPTS = 4


def _train_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    train = root / "train"
    if str(train) not in sys.path:
        sys.path.insert(0, str(train))


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
    return None


def _response_text(response) -> str:
    if isinstance(response, dict):
        return str(response.get("text") or "")
    parts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "\n".join(parts)


def _usage_dict(response) -> dict:
    if isinstance(response, dict):
        usage = response.get("usage") or {}
        return dict(usage) if isinstance(usage, dict) else {}
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    return {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_creation_input_tokens": int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        "cache_read_input_tokens": int(getattr(usage, "cache_read_input_tokens", 0) or 0),
    }


def teacher_request(system: str, user: str) -> dict:
    """Opus request. The system prompt is cached. Thinking stays on at low effort."""
    return {
        "model": TEACHER_MODEL,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "output_config": {"effort": "low"},
        "system": [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": user}],
    }


def cache_key(model: str, system: str, user: str) -> str:
    blob = json.dumps({"model": model, "system": system, "user": user}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def worst_case_usd(system: str, user: str):
    """Reserve the full input price plus a max_tokens output. No cache discount."""
    _train_on_path()
    from decimal import Decimal

    from guardtrain.prices import lookup_price
    from guardtrain.prompts import estimate_tokens

    price = lookup_price(TEACHER_MODEL)
    million = Decimal(1_000_000)
    input_tokens = estimate_tokens(system) + estimate_tokens(user)
    return (
        Decimal(input_tokens) * price.input_usd_per_mtok / million
        + Decimal(MAX_OUTPUT_TOKENS) * price.output_usd_per_mtok / million
    )


def _parse_teacher(text: str) -> dict | None:
    _train_on_path()
    from guardtrain.schema import OUTPUT_KEYS

    raw = text or ""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    if any(key not in obj for key in OUTPUT_KEYS):
        return None
    return {key: "" if obj.get(key) is None else str(obj.get(key)) for key in OUTPUT_KEYS}


def _keep_teacher(parsed: dict, row, gold: dict) -> bool:
    _train_on_path()
    from guardtrain.prompts import dump_output, estimate_tokens, shopper_page_text

    if parsed.get("verdict") != gold.get("verdict"):
        return False
    rendered = dump_output(parsed)
    if estimate_tokens(rendered) > MAX_TARGET_TOKENS:
        return False
    evidence = parsed.get("evidence") or ""
    if gold.get("verdict") == "pass":
        return evidence == "" and (parsed.get("instruction") or "") == ""
    if not evidence:
        return False
    page = row.page_text or ""
    shopper = shopper_page_text(page, row.page_id or "")
    return evidence in page or evidence in shopper


def _call_with_retry(create_fn, request: dict, sleeper, attempts: int = RETRY_ATTEMPTS):
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return create_fn(**request)
        except Exception as exc:  # noqa: BLE001
            last = exc
            status = _status_of(exc)
            if status not in RETRY_STATUSES or attempt + 1 >= attempts:
                raise
            sleeper(attempt)
    if last is not None:
        raise last
    raise RuntimeError("teacher call failed")


def _refuse_forbidden(rows, labels_path: Path, root: Path) -> None:
    _train_on_path()
    from guardtrain.data import discover_frozen_ids
    from guardtrain.schema import FORBIDDEN_SPLITS, FORBIDDEN_TRAIN_PAGE_SETS

    parts = {part.lower() for part in labels_path.parts}
    if "testset" in parts or labels_path.parent.name == "dev":
        raise SystemExit(
            "Distillation reads train pages only. Refusing a dev or testset labels file."
        )
    frozen = discover_frozen_ids(root)
    leaked = []
    for row in rows:
        if row.page_id in frozen or row.split in FORBIDDEN_SPLITS or row.split == "dev":
            leaked.append(row.page_id)
        elif row.page_set in FORBIDDEN_TRAIN_PAGE_SETS or row.page_set == "dev":
            leaked.append(row.page_id)
    if leaked:
        shown = ", ".join(leaked[:8])
        raise SystemExit(
            "Distillation refuses dev and frozen-test pages. "
            f"Found {shown}."
        )


def _live_create():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY is not set. Distillation runs on the box that has the key."
        )
    from anthropic import Anthropic

    return Anthropic(max_retries=0).messages.create


def distill_round(
    *,
    round_index: int,
    labels: Path,
    out: Path | None = None,
    max_usd: str = DEFAULT_MAX_USD,
    ledger_path: Path | None = None,
    cache_dir: Path | None = None,
    pages_dir: Path | None = None,
    repo: Path | None = None,
    create_fn=None,
    sleeper=None,
    workers: int = MAX_WORKERS,
) -> dict:
    """Label every train page. Keep a short teacher JSON only when the verdict matches."""
    _train_on_path()
    from guardtrain.data import attach_page_text, load_labels, resolve_pages_dir, write_jsonl
    from guardtrain.ledger import SpendLedger, shared_teacher_cache_dir, shared_teacher_ledger_path
    from guardtrain.paths import repo_root
    from guardtrain.prices import opus_teacher_cost
    from guardtrain.prompts import SYSTEM_PROMPT, build_user_message, dump_output, gold_object

    if round_index < 1:
        raise SystemExit("Distillation rounds start at 1.")
    root = repo or repo_root()
    labels = Path(labels)
    if not labels.is_file():
        raise SystemExit(f"Train labels not found: {labels}")
    rows = load_labels(labels)
    pages = resolve_pages_dir(labels, pages_dir)
    attach_page_text(rows, pages, required=True)
    _refuse_forbidden(rows, labels, root)
    destination = out or (labels.parent / "distilled.jsonl")
    ledger = SpendLedger(
        Path(ledger_path) if ledger_path else shared_teacher_ledger_path(),
        max_usd,
        quant="micro",
    )
    cache_root = Path(cache_dir) if cache_dir else shared_teacher_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    pause = sleeper or (lambda _attempt: None)
    limit = max(1, min(int(workers), MAX_WORKERS))
    system = SYSTEM_PROMPT

    def cached(user: str) -> dict | None:
        path = cache_root / f"{cache_key(TEACHER_MODEL, system, user)}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def store_cache(user: str, payload: dict) -> None:
        path = cache_root / f"{cache_key(TEACHER_MODEL, system, user)}.json"
        path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    calls = {"n": 0, "agreed": 0, "kept": 0, "cache_hits": 0, "stopped": False}
    lock = threading.Lock()
    inflight = {"n": 0, "max": 0}

    def finish(row, user: str, raw: str, usage: dict | None, entry_id: str | None) -> dict:
        gold = gold_object(row)
        parsed = _parse_teacher(raw)
        agreed = bool(parsed and parsed.get("verdict") == gold.get("verdict"))
        if parsed and _keep_teacher(parsed, row, gold):
            target = dump_output(parsed)
            source = "teacher"
        else:
            target = dump_output(gold)
            source = "label"
        if entry_id is not None:
            try:
                cost = opus_teacher_cost(usage)
            except Exception:
                ledger.release(entry_id, note="could not price the teacher response")
                raise
            ledger.settle(entry_id, cost, job_id=row.page_id)
        record = {
            "page_id": row.page_id,
            "target": target,
            "source": source,
            "verdict_agreement": agreed,
        }
        store_cache(user, record)
        with lock:
            calls["n"] += 1
            if agreed:
                calls["agreed"] += 1
            if source == "teacher":
                calls["kept"] += 1
        return record

    def work(row, user: str, entry_id: str) -> dict:
        with lock:
            inflight["n"] += 1
            inflight["max"] = max(inflight["max"], inflight["n"])
        try:
            if create_fn is None:
                caller = _live_create()
            else:
                caller = create_fn
            response = _call_with_retry(caller, teacher_request(system, user), pause)
            return finish(row, user, _response_text(response), _usage_dict(response), entry_id)
        except Exception:
            ledger.release(entry_id, note="teacher call failed")
            gold = gold_object(row)
            with lock:
                calls["n"] += 1
            return {
                "page_id": row.page_id,
                "target": dump_output(gold),
                "source": "label",
                "verdict_agreement": False,
            }
        finally:
            with lock:
                inflight["n"] -= 1

    ordered: list[dict | None] = [None] * len(rows)
    futures = []
    executor = ThreadPoolExecutor(max_workers=limit)
    try:
        for index, row in enumerate(rows):
            user = build_user_message(row)
            hit = cached(user)
            if hit and hit.get("target"):
                ordered[index] = {
                    "page_id": row.page_id,
                    "target": hit["target"],
                    "source": hit.get("source") or "label",
                    "verdict_agreement": bool(hit.get("verdict_agreement")),
                }
                with lock:
                    calls["cache_hits"] += 1
                    calls["n"] += 1
                    if hit.get("verdict_agreement"):
                        calls["agreed"] += 1
                    if hit.get("source") == "teacher":
                        calls["kept"] += 1
                continue
            reserve = worst_case_usd(system, user)
            if ledger.would_exceed(reserve, max_usd):
                calls["stopped"] = True
                gold = gold_object(row)
                ordered[index] = {
                    "page_id": row.page_id,
                    "target": dump_output(gold),
                    "source": "label",
                    "verdict_agreement": False,
                    "skipped": "cap",
                }
                for rest, later in enumerate(rows[index + 1 :], start=index + 1):
                    gold_later = gold_object(later)
                    ordered[rest] = {
                        "page_id": later.page_id,
                        "target": dump_output(gold_later),
                        "source": "label",
                        "verdict_agreement": False,
                        "skipped": "cap",
                    }
                break
            if create_fn is None and not os.environ.get("ANTHROPIC_API_KEY"):
                raise SystemExit(
                    "ANTHROPIC_API_KEY is not set. Distillation runs on the box that has the key."
                )
            entry_id = ledger.authorize(reserve, note=f"opus teacher {row.page_id}", requested_cap=max_usd)
            futures.append((index, executor.submit(work, row, user, entry_id)))
        for index, future in futures:
            ordered[index] = future.result()
    finally:
        executor.shutdown(wait=True)

    written = [row for row in ordered if row is not None]
    write_jsonl(destination, written)
    asked = calls["n"]
    agreement = (calls["agreed"] / asked) if asked else 0.0
    result = {
        "round": round_index,
        "model": TEACHER_MODEL,
        "rows": len(written),
        "teacher_kept": calls["kept"],
        "asked": asked,
        "agreement_rate": agreement,
        "cache_hits": calls["cache_hits"],
        "stopped_for_cap": calls["stopped"],
        "max_usd": str(max_usd),
        "workers": limit,
        "max_inflight": inflight["max"],
        "out": str(destination),
        "ledger": str(ledger.path),
    }
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Distill claude-opus-5-5 onto this round's train pages. Hard-stops at the cumulative cap."
    )
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--max-usd", default=DEFAULT_MAX_USD, help="Cumulative teacher cap. Default 50.")
    parser.add_argument("--labels", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--pages-dir", default=None)
    parser.add_argument("--ledger", default=None)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    labels = Path(args.labels) if args.labels else root / "data" / "trainset" / f"round{args.round}" / "labels.jsonl"
    distill_round(
        round_index=args.round,
        labels=labels,
        out=Path(args.out) if args.out else None,
        max_usd=str(args.max_usd),
        ledger_path=Path(args.ledger) if args.ledger else None,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        pages_dir=Path(args.pages_dir) if args.pages_dir else None,
        repo=root,
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
