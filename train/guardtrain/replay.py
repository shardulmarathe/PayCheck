"""Per-round replay log for the demo training view.

``runs/r{N}/replay.jsonl`` has one line per train or dev page. Test pages are
refused. ``runs/r{N}/summary.json`` uses the pinned key set the showcase reads.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from guardtrain.data import write_jsonl
from guardtrain.schema import FORBIDDEN_SPLITS, FORBIDDEN_TRAIN_PAGE_SETS, ContractError, LabelRow
from guardtrain.scoring import score_predictions
from guardtrain.selection import trick_scores

REPLAY_KEYS = (
    "round",
    "page_id",
    "store",
    "page_kind",
    "trick",
    "split",
    "label",
    "verdict",
    "correct",
    "fed_back",
    "source",
)
SCORE_KEYS = ("catch_rate", "false_block_rate", "f1", "n")
SUMMARY_KEYS = (
    "round",
    "winner_trial",
    "new_pages",
    "seeded_from_misses",
    "train",
    "dev",
    "test",
    "in_dist_vs_heldout_template_gap",
)
TEST_SLICE_ORDER = ("in_dist", "heldout_template", "heldout_attack")
HEADLINE_SLICE = "heldout_template"
_PUBLIC_ID = re.compile(r"^p-[0-9a-f]{8}$")
_TEST_SLICES = frozenset(TEST_SLICE_ORDER)


def replay_dir(runs: Path, round_index: int) -> Path:
    return Path(runs) / f"r{int(round_index)}"


def neutral_page_id(row: LabelRow) -> str:
    """Public id. Legacy ids are hashed to ``p-`` plus 8 hex and are not stored."""
    current = row.page_id or ""
    if _PUBLIC_ID.match(current):
        return current
    legacy = str((row.extra or {}).get("legacy_page_id") or current)
    from guardtrain.paths import repo_root
    import sys

    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    from gym.ids import public_page_id

    return public_page_id(legacy)


def _row_ids(row: LabelRow, public: str) -> set[str]:
    found = {public}
    if row.page_id:
        found.add(row.page_id)
    legacy = (row.extra or {}).get("legacy_page_id")
    if legacy:
        found.add(str(legacy))
    return {item for item in found if item}


def _refuse_test_page(row: LabelRow, public: str, frozen_ids: set[str]) -> None:
    if row.split in FORBIDDEN_SPLITS or row.page_set in FORBIDDEN_TRAIN_PAGE_SETS:
        raise ContractError(
            f"Refusing to write test page {row.page_id or public} into replay.jsonl."
        )
    slice_name = str((row.extra or {}).get("slice") or "")
    if slice_name in _TEST_SLICES:
        raise ContractError(
            f"Refusing to write frozen slice {slice_name} page {public} into replay.jsonl."
        )
    leaked = sorted(_row_ids(row, public) & set(frozen_ids))
    if leaked:
        shown = ", ".join(leaked[:8])
        raise ContractError(f"Refusing to write frozen test page id into replay.jsonl: {shown}")


def _source_of(row: LabelRow) -> str:
    if row.mix_source in {"miss", "replay"} or (row.extra or {}).get("seeded_from_miss"):
        return "from_miss"
    return "fresh"


def _kind_and_store(row: LabelRow, spec: dict | None) -> tuple[str, str]:
    store = str((row.extra or {}).get("store_name") or row.store or "")
    kind = str((row.extra or {}).get("page_kind") or "")
    if spec:
        brand = (spec.get("store") or {}).get("brand")
        if brand:
            store = str(brand)
        spec_kind = (spec.get("page") or {}).get("kind")
        if spec_kind:
            kind = str(spec_kind)
    if not kind:
        for line in (row.page_text or "").splitlines():
            if line.startswith("kind:"):
                kind = line.split(":", 1)[1].strip()
                break
    return store, kind


def _load_specs(directories: list[Path] | None) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for directory in directories or []:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(spec, dict):
                found[str(spec.get("page_id") or path.stem)] = spec
    return found


def _normalize_pred(pred: dict | None) -> dict:
    out = dict(pred or {})
    out.setdefault("verdict", "pass")
    out.setdefault("attack_type", "none")
    out.setdefault("evidence", "")
    out.setdefault("instruction", "")
    out.setdefault("parse_ok", True)
    out.setdefault("latency_ms", 0)
    out.setdefault("cost_usd", "0")
    out.setdefault("input_tokens", 0)
    out.setdefault("output_tokens", 0)
    out.setdefault("raw", "")
    return out


def _is_miss(row: LabelRow, pred: dict) -> bool:
    verdict = pred.get("verdict") or "pass"
    attack = pred.get("attack_type") or "none"
    if not pred.get("parse_ok", True):
        return True
    if verdict != row.verdict:
        return True
    if row.verdict == "block" and attack != (row.attack_type or "none"):
        return True
    return False


def _empty_score() -> dict:
    return {"catch_rate": None, "false_block_rate": None, "f1": None, "n": 0}


def score_block(rows: list[LabelRow], preds: list[dict], *, attack_only: bool = False) -> dict:
    """The four summary numbers. ``heldout_attack`` has no clean pages, so its false-block rate is null."""
    if not rows:
        block = _empty_score()
        if attack_only:
            block["false_block_rate"] = None
        return block
    metrics = score_predictions(rows, preds)
    tricks = trick_scores(metrics)
    false_block = tricks["false_block_rate_clean"]
    if attack_only or not tricks["n_clean"]:
        false_block = None
    return {
        "catch_rate": metrics["catch_rate"],
        "false_block_rate": false_block,
        "f1": tricks["trick_f1"],
        "n": metrics["n"],
    }


def _gap(in_dist: dict, heldout_template: dict):
    left = in_dist.get("f1")
    right = heldout_template.get("f1")
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return None
    return left - right


def slice_blocks(rows: list[LabelRow], preds: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[tuple[LabelRow, dict]]] = {name: [] for name in TEST_SLICE_ORDER}
    for row, pred in zip(rows, preds):
        name = str((row.extra or {}).get("slice") or "")
        if name in grouped:
            grouped[name].append((row, pred))
    blocks = {}
    for name in TEST_SLICE_ORDER:
        pairs = grouped[name]
        blocks[name] = score_block(
            [row for row, _pred in pairs],
            [pred for _row, pred in pairs],
            attack_only=(name == "heldout_attack"),
        )
    return blocks


def headline_slice_report(blocks: dict[str, dict]) -> dict[str, dict]:
    """Eval output leads with ``heldout_template``. ``heldout_attack`` is recall only."""
    ordered = {}
    for name in (HEADLINE_SLICE, "in_dist", "heldout_attack"):
        block = dict(blocks.get(name) or _empty_score())
        if name == "heldout_attack":
            block["false_block_rate"] = None
            block["recall"] = block.get("catch_rate")
            block["primary"] = "recall"
        else:
            block["primary"] = "f1"
        ordered[name] = block
    return ordered


def _candidate_rows(
    train_rows: list[LabelRow],
    dev_rows: list[LabelRow],
    mix_rows: list[LabelRow] | None,
) -> list[tuple[LabelRow, str]]:
    """Train and dev pages only. Mix rows carry ``from_miss`` for seeded misses."""
    if mix_rows is not None:
        tagged = [(row, "train") for row in mix_rows]
    else:
        tagged = [(row, "train") for row in train_rows]
    tagged.extend((row, "dev") for row in dev_rows)
    return tagged


def write_round_logs(
    runs: Path,
    *,
    round_index: int,
    train_rows: list[LabelRow],
    dev_rows: list[LabelRow],
    test_rows: list[LabelRow],
    predict,
    winner_trial: str | None,
    frozen_ids: set[str],
    mix_rows: list[LabelRow] | None = None,
    spec_dirs: list[Path] | None = None,
) -> dict:
    """Write ``replay.jsonl`` and the pinned ``summary.json``. Test pages stay out of the replay."""
    specs = _load_specs(spec_dirs)
    lines = []
    replay_rows: list[LabelRow] = []
    replay_preds: list[dict] = []
    for row, bucket in _candidate_rows(train_rows, dev_rows, mix_rows):
        public = neutral_page_id(row)
        _refuse_test_page(row, public, frozen_ids)
        pred = _normalize_pred(predict(row))
        spec = specs.get(public) or specs.get(row.page_id or "")
        store, kind = _kind_and_store(row, spec)
        source = _source_of(row)
        split = "dev" if bucket == "dev" else "train"
        label = row.verdict or "pass"
        verdict = pred.get("verdict") or "pass"
        correct = bool(pred.get("parse_ok", True)) and verdict == label
        fed_back = split == "dev" and _is_miss(row, pred)
        line = {
            "round": int(round_index),
            "page_id": public,
            "store": store,
            "page_kind": kind,
            "trick": row.attack_type or "none",
            "split": split,
            "label": label,
            "verdict": verdict,
            "correct": correct,
            "fed_back": fed_back,
            "source": source,
        }
        if tuple(line) != REPLAY_KEYS:
            raise RuntimeError("replay.jsonl line keys drifted from the pinned list")
        lines.append(line)
        replay_rows.append(row)
        replay_preds.append(pred)

    lines.sort(key=lambda item: (0 if item["split"] == "train" else 1, item["page_id"]))
    # Predictions were taken before the sort. Rebuild aligned rows in that order.
    by_public = {neutral_page_id(row): (row, pred) for row, pred in zip(replay_rows, replay_preds)}
    ordered_rows = []
    ordered_preds = []
    for line in lines:
        row, pred = by_public[line["page_id"]]
        ordered_rows.append(row)
        ordered_preds.append(pred)

    train_pairs = [(row, pred) for row, pred, line in zip(ordered_rows, ordered_preds, lines) if line["split"] == "train"]
    dev_pairs = [(row, pred) for row, pred, line in zip(ordered_rows, ordered_preds, lines) if line["split"] == "dev"]
    test_preds = [_normalize_pred(predict(row)) for row in test_rows]
    blocks = slice_blocks(test_rows, test_preds)
    summary = {
        "round": int(round_index),
        "winner_trial": winner_trial if winner_trial else None,
        "new_pages": sum(1 for line in lines if line["source"] == "fresh"),
        "seeded_from_misses": sum(1 for line in lines if line["source"] == "from_miss"),
        "train": score_block([row for row, _pred in train_pairs], [pred for _row, pred in train_pairs]),
        "dev": score_block([row for row, _pred in dev_pairs], [pred for _row, pred in dev_pairs]),
        "test": {name: blocks[name] for name in TEST_SLICE_ORDER},
        "in_dist_vs_heldout_template_gap": _gap(blocks["in_dist"], blocks["heldout_template"]),
    }
    if tuple(summary) != SUMMARY_KEYS:
        raise RuntimeError("summary.json keys drifted from the pinned schema")
    for name in ("train", "dev", *TEST_SLICE_ORDER):
        block = summary[name] if name in ("train", "dev") else summary["test"][name]
        if tuple(block) != SCORE_KEYS:
            raise RuntimeError(f"summary {name} keys drifted from the pinned score schema")
    if summary["test"]["heldout_attack"]["false_block_rate"] is not None:
        raise RuntimeError("heldout_attack.false_block_rate must be null")

    directory = replay_dir(runs, round_index)
    directory.mkdir(parents=True, exist_ok=True)
    replay_path = directory / "replay.jsonl"
    summary_path = directory / "summary.json"
    write_jsonl(replay_path, lines)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    leaked = [line["page_id"] for line in lines if line["page_id"] in frozen_ids]
    if leaked:
        raise ContractError(f"replay.jsonl contains frozen test ids: {leaked[:8]}")
    return {
        "replay_path": replay_path,
        "summary_path": summary_path,
        "summary": summary,
        "lines": lines,
        "by_slice": headline_slice_report(blocks),
        "headline_slice": HEADLINE_SLICE,
    }
