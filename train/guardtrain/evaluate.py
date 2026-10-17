"""Score a guard on the frozen test set and the 100-page slice."""

from __future__ import annotations

import json
import random
import re
from decimal import Decimal
from pathlib import Path
from typing import Callable

from guardtrain.clients import ApiCallError, CheckResult
from guardtrain.data import load_id_list, load_labels
from guardtrain.ledger import SpendLedger
from guardtrain.prices import ModelPrice
from guardtrain.prompts import build_messages, estimate_tokens
from guardtrain.schema import FORBIDDEN_TRAIN_PAGE_SETS, LabelRow
from guardtrain.replay import HEADLINE_SLICE, headline_slice_report, slice_blocks
from guardtrain.scoring import score_predictions

Checker = Callable[[LabelRow], CheckResult]


def safe_model_name(model: str) -> str:
    name = model.strip().lower().replace("/", "-")
    name = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-")
    return name or "model"


def prompt_token_estimate(row: LabelRow, max_page_tokens: int) -> int:
    messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
    return sum(estimate_tokens(message["content"]) for message in messages)


def select_ids(rows: list[LabelRow], ids: list[str]) -> list[LabelRow]:
    wanted = set(ids)
    return [row for row in rows if row.page_id in wanted]


def probe_sample(rows: list[LabelRow], n: int, seed: int) -> list[LabelRow]:
    picked = list(rows)
    random.Random(seed).shuffle(picked)
    return picked[:n]


def prepare_page_set(
    rows: list[LabelRow],
    *,
    model: str = "",
    slice_ids: list[str] | None = None,
    allow_full: bool = False,
    probe: int | None = None,
    seed: int = 0,
    page_set: str = "testset",
) -> tuple[list[LabelRow], str]:
    """Pick the pages a baseline is allowed to score.

    ``gemini-3.1-pro-preview`` stays on the 100-page slice unless
    ``allow_full`` is set. ``probe`` draws a repeatable sample and stops there.
    """
    from guardtrain.prices import PRO_GEMINI_MODELS
    from guardtrain.schema import ContractError

    selected = list(rows)
    chosen = page_set
    if model in PRO_GEMINI_MODELS and not allow_full:
        if not slice_ids:
            raise ContractError(
                "gemini-3.1-pro-preview is restricted to the 100-page slice. "
                "Pass --slice gym/testset/slice100.txt. "
                "--allow-full-testset overrides this and can spend the Gemini cap quickly."
            )
        selected = select_ids(selected, slice_ids)
        chosen = "slice100"
        if not selected:
            raise ContractError("None of the slice ids were found in --labels.")
    elif slice_ids and page_set == "slice100":
        selected = select_ids(selected, slice_ids)
        chosen = "slice100"
    if probe:
        if probe < 1:
            raise ContractError("--probe must be >= 1")
        selected = probe_sample(selected, probe, seed)
        chosen = "probe" if chosen == "testset" else f"{chosen}-probe"
    return selected, chosen


def _money(value: Decimal) -> str:
    return format(value, "f")


def run_checks(
    rows: list[LabelRow],
    checker: Checker,
    *,
    price: ModelPrice,
    max_output_tokens: int,
    max_page_tokens: int,
    ledger: SpendLedger | None = None,
    requested_cap: str | None = None,
) -> tuple[list[dict], str | None]:
    """Run checks until the spend cap cannot authorize the next worst-case call."""
    preds: list[dict] = []
    stopped: str | None = None
    for row in rows:
        estimate_in = prompt_token_estimate(row, max_page_tokens)
        worst = price.cost(estimate_in, max_output_tokens)
        entry_id = None
        if ledger is not None:
            try:
                entry_id = ledger.authorize(
                    worst,
                    note=f"check {row.page_id}",
                    requested_cap=requested_cap,
                )
            except Exception as exc:
                from guardtrain.ledger import SpendCapExceeded

                if isinstance(exc, SpendCapExceeded):
                    stopped = str(exc)
                    break
                raise
        try:
            result = checker(row)
        except ApiCallError as exc:
            if ledger is not None and entry_id is not None:
                if exc.sent:
                    ledger.settle(entry_id, worst)
                else:
                    ledger.release(entry_id)
            preds.append(
                {
                    "verdict": "pass",
                    "attack_type": "none",
                    "evidence": "",
                    "instruction": "",
                    "parse_ok": False,
                    "latency_ms": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": _money(worst if exc.sent else Decimal("0")),
                    "error": str(exc),
                    "raw": "",
                }
            )
            continue
        actual_in = result.input_tokens
        actual_out = result.output_tokens
        if result.sent and actual_in == 0 and actual_out == 0:
            cost = worst
        else:
            cost = price.cost(actual_in, actual_out)
        if ledger is not None and entry_id is not None:
            ledger.settle(entry_id, cost)
        pred = result.as_pred()
        pred["cost_usd"] = _money(cost)
        preds.append(pred)
    return preds, stopped


def read_testset_content_hash(root: Path | None = None) -> dict:
    """Read ``gym/testset/manifest.json`` at runtime. The hash is not hardcoded."""
    from guardtrain.paths import repo_root

    root = root or repo_root()
    path = root / "gym" / "testset" / "manifest.json"
    info: dict = {"manifest": str(path), "content_hash": None}
    if not path.is_file():
        return info
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        info["error"] = "manifest is not JSON"
        return info
    value = payload.get("content_hash")
    if isinstance(value, str) and value:
        info["content_hash"] = value
    return info


def build_report(
    *,
    model: str,
    round_name: str,
    page_set: str,
    rows: list[LabelRow],
    preds: list[dict],
    price: ModelPrice,
    stopped_reason: str | None,
    extra: dict | None = None,
) -> dict:
    metrics = score_predictions(rows[: len(preds)], preds)
    trainable = page_set not in FORBIDDEN_TRAIN_PAGE_SETS and "probe" not in page_set
    testset = read_testset_content_hash()
    report = {
        "schema_version": 1,
        "model": model,
        "round": round_name,
        "page_set": page_set,
        "n": metrics["n"],
        "not_for_training": not trainable,
        "testset_content_hash": testset["content_hash"],
        "testset_manifest": testset["manifest"],
        "exclude_from_leaderboard": model == "mock-guard" or str(model).startswith("mock"),
        "stopped_reason": stopped_reason,
        "price": price.as_dict(),
        "metrics": {key: value for key, value in metrics.items() if key != "pages"},
        "per_attack_type": metrics["per_attack_type"],
        "per_family": metrics["per_family"],
        "cost_per_check_usd": metrics["cost_per_check_usd"],
        "cost_per_1000_checks_usd": metrics["cost_per_1000_checks_usd"],
        "catch_rate": metrics["catch_rate"],
        "false_block_rate_clean": metrics["false_block_rate_clean"],
        "evidence_quote_match": metrics["evidence_quote_match"],
        "pages": metrics["pages"],
    }
    scored_rows = rows[: len(preds)]
    if any((row.extra or {}).get("slice") for row in scored_rows):
        report["headline_slice"] = HEADLINE_SLICE
        report["by_slice"] = headline_slice_report(slice_blocks(scored_rows, preds))
    if extra:
        report["extra"] = extra
    return report


def eval_filename(model: str, round_name: str, page_set: str) -> str:
    base = f"{safe_model_name(model)}_{round_name}"
    if page_set == "slice100":
        return f"{base}_slice100.json"
    if page_set not in {"testset", "dev", "train"}:
        return f"{base}_{page_set}.json"
    return f"{base}.json"


def write_report(runs: Path, report: dict) -> Path:
    extra = report.get("extra") or {}
    rows_by_id = extra.pop("rows_by_id", None)
    out = runs / "eval" / eval_filename(report["model"], str(report["round"]), report["page_set"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_misses(runs, report, rows_by_id=rows_by_id)
    update_leaderboard(runs)
    return out


def write_misses(runs: Path, report: dict, *, rows_by_id: dict | None = None) -> Path | None:
    pages = report.get("pages") or []
    misses = [page for page in pages if page.get("miss")]
    name = eval_filename(report["model"], str(report["round"]), report["page_set"])
    path = runs / "eval" / name.replace(".json", ".misses.jsonl")
    if report.get("not_for_training", True):
        # Page ids only. The round loader rejects not_for_training and frozen page sets.
        with path.open("w", encoding="utf-8") as handle:
            for page in misses:
                handle.write(
                    json.dumps(
                        {
                            "page_id": page["page_id"],
                            "page_set": report["page_set"],
                            "not_for_training": True,
                        }
                    )
                    + "\n"
                )
        return path
    # Trainable misses (dev / train) keep the fields the next round needs.
    # The caller passes full rows through report extra when available.
    rows_by_id = rows_by_id or {}
    with path.open("w", encoding="utf-8") as handle:
        for page in misses:
            raw_row = dict(rows_by_id.get(page["page_id"]) or {"page_id": page["page_id"]})
            raw_row["page_set"] = report["page_set"]
            raw_row["model_output"] = page.get("raw_output") or json.dumps(
                {
                    "verdict": page.get("verdict"),
                    "attack_type": page.get("attack_type"),
                    "evidence": page.get("evidence") or "",
                    "instruction": page.get("instruction") or "",
                },
                ensure_ascii=False,
            )
            raw_row["not_for_training"] = False
            handle.write(json.dumps(raw_row, ensure_ascii=False) + "\n")
    return path


def rows_by_id_map(rows: list[LabelRow]) -> dict[str, dict]:
    return {row.page_id: row.as_dict() for row in rows}


def update_leaderboard(runs: Path) -> Path:
    eval_dir = runs / "eval"
    eval_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for path in sorted(eval_dir.glob("*.json")):
        if path.name == "leaderboard.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if "model" not in payload or "page_set" not in payload:
            continue
        if payload.get("exclude_from_leaderboard") or payload.get("model") == "mock-guard":
            continue
        metrics = payload.get("metrics") or {}
        rows.append(
            {
                "model": payload.get("model"),
                "round": payload.get("round"),
                "page_set": payload.get("page_set"),
                "n": payload.get("n"),
                "catch_rate": payload.get("catch_rate"),
                "false_block_rate_clean": payload.get("false_block_rate_clean"),
                "evidence_quote_match": payload.get("evidence_quote_match"),
                "latency_ms_mean": metrics.get("latency_ms_mean"),
                "cost_per_check_usd": payload.get("cost_per_check_usd"),
                "cost_per_1000_checks_usd": payload.get("cost_per_1000_checks_usd"),
                "catch_rate_by_attack_type": {
                    name: bucket.get("catch_rate")
                    for name, bucket in (payload.get("per_attack_type") or {}).items()
                },
                "stopped_reason": payload.get("stopped_reason"),
                "path": str(path),
            }
        )
    rows.sort(
        key=lambda row: (
            -(row["catch_rate"] if isinstance(row["catch_rate"], (int, float)) else -1),
            row["cost_per_1000_checks_usd"] or "",
            str(row["model"]),
            str(row["page_set"]),
        )
    )
    path = eval_dir / "leaderboard.json"
    path.write_text(
        json.dumps({"schema_version": 1, "rows": rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_eval_rows(labels: Path, pages_dir: Path | None = None) -> list[LabelRow]:
    from guardtrain.data import attach_page_text, resolve_pages_dir

    rows = load_labels(labels)
    attach_page_text(rows, resolve_pages_dir(labels, pages_dir), required=True)
    return rows


def slice_ids_from(path: Path | None) -> list[str]:
    if path is None:
        return []
    return load_id_list(path)
