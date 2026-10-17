"""Replay documents the showcase site can animate, and the customer tally."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shopper.prompt import TEST_CARD_NUMBER
from shopper.schema import REPLAY_SCHEMA, TALLY_SCHEMA

_SECRETS = (TEST_CARD_NUMBER, "hunter2")

EXCERPT_CHARS = 1200

REAL_OUT = Path("runs/shopper")
SYNTHETIC_OUT = Path("runs/shopper/synthetic")


class MixedRunError(RuntimeError):
    """Synthetic and real runs cannot share one tally."""


def is_synthetic(*, mock: bool, mode: str, guard_backend: str | None) -> bool:
    """Mock shopper or mock guard. An unguarded live run is real even if a mock guard is configured."""
    if mock:
        return True
    return mode == "guarded" and guard_backend == "mock"


def output_dir(explicit: str | None, synthetic: bool) -> Path:
    """Explicit ``--out`` is used as given. Otherwise synthetic and real runs stay apart."""
    if explicit:
        return Path(explicit)
    return SYNTHETIC_OUT if synthetic else REAL_OUT


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def redact(text: str) -> str:
    """Keep card numbers and the mock bank password out of replay files."""
    for secret in _SECRETS:
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    return text


def excerpt(text: str, limit: int = EXCERPT_CHARS) -> str:
    text = redact(text or "")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[truncated]\n"


def relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


_MASK_JS = """() => {
  let style = document.getElementById("shopper-field-mask");
  if (!style) {
    style = document.createElement("style");
    style.id = "shopper-field-mask";
    style.textContent = "input, textarea { -webkit-text-security: disc !important; color: transparent !important; caret-color: transparent !important; }";
    (document.head || document.documentElement).appendChild(style);
  }
  return "ok";
}"""

_UNMASK_JS = """() => {
  const style = document.getElementById("shopper-field-mask");
  if (style) style.remove();
  return "ok";
}"""


async def _png_bytes(page) -> bytes:
    """Screenshot a browser-use page without leaving typed secrets in the pixels."""
    import base64

    try:
        await page.evaluate(_MASK_JS)
    except Exception:
        pass
    try:
        data = await page.screenshot(format="png")
    finally:
        try:
            await page.evaluate(_UNMASK_JS)
        except Exception:
            pass
    if isinstance(data, bytes):
        return data
    return base64.b64decode(data)


class RunLog:
    def __init__(self, out_dir: Path, errand_id: str, mode: str) -> None:
        self.out_dir = out_dir
        self.errand_id = errand_id
        self.mode = mode
        self.shot_dir = out_dir / "shots"
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[dict[str, Any]] = []

    async def screenshot(self, page) -> str | None:
        dest = self.shot_dir / f"{self.errand_id}_{self.mode}_{len(self.steps):03d}.webp"
        try:
            from io import BytesIO

            from PIL import Image

            raw = await _png_bytes(page)
            image = Image.open(BytesIO(raw))
            image.save(dest, format="WEBP", quality=55, method=4)
        except Exception:
            return None
        return relpath(dest, self.out_dir)

    def add(
        self,
        *,
        url: str,
        action: str,
        page_text: str,
        screenshot: str | None,
        target: dict | None = None,
        guard: dict | None = None,
        blocked: bool = False,
        viewport: dict | None = None,
        evidence_bbox: list[int] | None = None,
    ) -> None:
        safe_target = None
        if target is not None:
            safe_target = {
                "selector": redact(str(target.get("selector") or "")),
                "text": redact(str(target.get("text") or "")),
                "bbox": target.get("bbox"),
            }
        self.steps.append(
            {
                "index": len(self.steps),
                "timestamp": now_iso(),
                "url": url,
                "action": redact(action),
                "target": safe_target,
                "screenshot": screenshot,
                "page_text_excerpt": excerpt(page_text),
                "guard": guard,
                "blocked": blocked,
                "viewport": {
                    "width": int((viewport or {}).get("width") or 1280),
                    "height": int((viewport or {}).get("height") or 800),
                },
                "evidence_bbox": evidence_bbox,
            }
        )


def target_from(selector: str, text: str, bbox: list[int] | None) -> dict:
    return {"selector": selector, "text": text, "bbox": bbox}


def guard_record(*, endpoint: str, backend: str, latency_ms: float | None, action: str, response: dict) -> dict:
    # A mock check is not a measured round trip. Leave latency_ms null.
    recorded = None if backend == "mock" else latency_ms
    return {
        "endpoint": endpoint,
        "backend": backend,
        "latency_ms": recorded,
        "action": action,
        "response": {
            "verdict": response["verdict"],
            "attack_type": response["attack_type"],
            "evidence": response["evidence"],
            "instruction": response["instruction"],
        },
    }


def assemble(
    *,
    errand_id: str,
    mode: str,
    mock: bool,
    synthetic: bool,
    run_id: str,
    model: str,
    instruction: str,
    start_url: str,
    guard_backend: str | None,
    attack_type: str,
    started_at: str,
    steps: list[dict],
    scored: dict,
    usd_spent: float,
    video: str | None,
    error: str | None,
    hero_addon_usd: float | None = None,
) -> dict:
    document = {
        "schema_version": "1",
        "errand_id": errand_id,
        "mode": mode,
        "mock": mock,
        "synthetic": synthetic,
        "run_id": run_id,
        "model": model,
        "instruction": instruction,
        "start_url": start_url,
        "guard_backend": guard_backend,
        "attack_type": attack_type,
        "started_at": started_at,
        "finished_at": now_iso(),
        "steps": steps,
        "final_cart": scored["final_cart"],
        "correct": scored["correct"],
        "amount_charged_cents": scored["amount_charged_cents"],
        "correct_total_cents": scored["correct_total_cents"],
        "scams_fallen_for": scored["scams_fallen_for"],
        "unwanted_items": scored["unwanted_items"],
        "unwanted_subscription": scored["unwanted_subscription"],
        "dollars_lost_cents": scored["dollars_lost_cents"],
        "dollars_lost": scored["dollars_lost"],
        "overcharge_usd": scored["overcharge_usd"],
        "exposed": scored["exposed"],
        "outcome": scored["outcome"],
        "matches_correct": scored["matches_correct"],
        "usd_spent": round(usd_spent, 6),
        "video": video,
        "error": error,
    }
    if hero_addon_usd is not None:
        document["hero_addon_usd"] = hero_addon_usd
    validate_replay(document)
    return document


def validate_replay(document: dict) -> None:
    import jsonschema

    jsonschema.validate(document, REPLAY_SCHEMA)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_replays(out_dir: Path) -> list[dict]:
    documents = []
    if not out_dir.is_dir():
        return documents
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "tally.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("schema_version") == "1" and payload.get("errand_id") and payload.get("mode"):
            documents.append(payload)
    return documents


def _empty_summary() -> dict:
    return {
        "runs": 0,
        "succeeded": 0,
        "fell": 0,
        "incomplete": 0,
        "stopped": 0,
        "errors": 0,
        "dollars_lost_cents": 0,
        "dollars_lost": 0.0,
        "overcharge_usd": 0.0,
        "amount_charged_cents": 0,
        "scams_fallen_for": 0,
        "unwanted_items": 0,
        "exposed": 0,
    }


def _add_run(summary: dict, run: dict) -> None:
    summary["runs"] += 1
    outcome = run.get("outcome")
    if outcome in {"protected", "clean"}:
        summary["succeeded"] += 1
    elif outcome == "fell":
        summary["fell"] += 1
    elif outcome == "incomplete":
        summary["incomplete"] += 1
    elif outcome == "stopped":
        summary["stopped"] += 1
    elif outcome == "error":
        summary["errors"] += 1
    summary["dollars_lost_cents"] += int(run.get("dollars_lost_cents") or 0)
    summary["amount_charged_cents"] += int(run.get("amount_charged_cents") or 0)
    summary["scams_fallen_for"] += len(run.get("scams_fallen_for") or [])
    summary["unwanted_items"] += len(run.get("unwanted_items") or [])
    if run.get("exposed"):
        summary["exposed"] += 1
    summary["dollars_lost"] = round(summary["dollars_lost_cents"] / 100, 2)
    summary["overcharge_usd"] = summary["dollars_lost"]


def build_tally(runs: list[dict], *, synthetic: bool, run_id: str) -> dict:
    without = _empty_summary()
    with_guard = _empty_summary()
    by_errand: dict[str, dict] = {}
    compact = []
    for run in runs:
        bucket = with_guard if run.get("mode") == "guarded" else without
        if run.get("mode") == "unguarded":
            bucket = without
        _add_run(bucket, run)
        errand_id = run["errand_id"]
        by_errand.setdefault(errand_id, {})[run["mode"]] = {
            "outcome": run.get("outcome"),
            "amount_charged_cents": run.get("amount_charged_cents"),
            "correct_total_cents": run.get("correct_total_cents"),
            "dollars_lost_cents": run.get("dollars_lost_cents"),
            "dollars_lost": run.get("dollars_lost"),
            "overcharge_usd": run.get("overcharge_usd"),
            "exposed": bool(run.get("exposed")),
            "scams_fallen_for": run.get("scams_fallen_for"),
            "unwanted_items": run.get("unwanted_items"),
            "matches_correct": run.get("matches_correct"),
        }
        compact.append(
            {
                "errand_id": errand_id,
                "mode": run.get("mode"),
                "outcome": run.get("outcome"),
                "dollars_lost": run.get("dollars_lost"),
                "overcharge_usd": run.get("overcharge_usd"),
                "exposed": bool(run.get("exposed")),
                "amount_charged_cents": run.get("amount_charged_cents"),
                "scams_fallen_for": run.get("scams_fallen_for"),
            }
        )
    document = {
        "schema_version": "1",
        "generated_at": now_iso(),
        "synthetic": synthetic,
        "run_id": run_id,
        "without_guard": without,
        "with_guard": with_guard,
        "by_errand": by_errand,
        "runs": compact,
    }
    import jsonschema

    jsonschema.validate(document, TALLY_SCHEMA)
    return document


def write_tally(out_dir: Path, run_id: str) -> dict:
    """Sum only this invocation. Stale files with another run_id are ignored."""
    runs = [doc for doc in load_replays(out_dir) if doc.get("run_id") == run_id]
    flags = {bool(doc.get("synthetic")) for doc in runs}
    if len(flags) > 1:
        raise MixedRunError("tally refuses to mix synthetic and real runs")
    synthetic = flags.pop() if flags else False
    document = build_tally(runs, synthetic=synthetic, run_id=run_id)
    write_json(out_dir / "tally.json", document)
    return document
