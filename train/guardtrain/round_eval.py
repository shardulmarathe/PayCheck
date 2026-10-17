"""Score one round on its train sample, its dev split, and the frozen test set.

The numbers land in ``runs/training/roundN.json`` so a train-dev gap is visible
before the next round. Misses written for that next round come only from dev.
"""

from __future__ import annotations

import json
from pathlib import Path

from guardtrain.data import discover_frozen_ids, load_id_list, write_jsonl
from guardtrain.early_stop import EARLY_STOP_METRIC, choose_stopped_epoch
from guardtrain.evaluate import read_testset_content_hash
from guardtrain.paths import repo_root
from guardtrain.replay import HEADLINE_SLICE, write_round_logs
from guardtrain.schema import ContractError, LabelRow
from guardtrain.scoring import score_predictions
from guardtrain.selection import trick_scores


def sample_train_rows(rows: list[LabelRow], n: int, seed: int) -> list[LabelRow]:
    """Stratified sample of the fresh train split. Stable for a given seed."""
    if n <= 0 or not rows:
        return []
    if len(rows) <= n:
        ordered = list(rows)
        ordered.sort(key=lambda row: row.page_id)
        return ordered
    grouped: dict[str, list[LabelRow]] = {}
    for row in rows:
        grouped.setdefault(row.attack_type, []).append(row)
    for group in grouped.values():
        group.sort(key=lambda row: row.page_id)
    import random

    rng = random.Random(seed)
    pools = []
    for key in sorted(grouped):
        pool = list(grouped[key])
        rng.shuffle(pool)
        pools.append(pool)
    picked: list[LabelRow] = []
    while len(picked) < n and any(pools):
        for pool in pools:
            if pool and len(picked) < n:
                picked.append(pool.pop())
    picked.sort(key=lambda row: row.page_id)
    return picked


def _diff(train_value, dev_value):
    if train_value is None or dev_value is None:
        return None
    if isinstance(train_value, (int, float)) and isinstance(dev_value, (int, float)):
        return train_value - dev_value
    return None


def train_dev_gap(train_summary: dict, dev_summary: dict) -> dict:
    """Positive catch_rate means the train sample looks better than dev."""
    return {
        "catch_rate": _diff(train_summary.get("catch_rate"), dev_summary.get("catch_rate")),
        "false_block_rate_clean": _diff(
            train_summary.get("false_block_rate_clean"),
            dev_summary.get("false_block_rate_clean"),
        ),
        "evidence_quote_match": _diff(
            train_summary.get("evidence_quote_match"),
            dev_summary.get("evidence_quote_match"),
        ),
    }


def summarize_metrics(metrics: dict) -> dict:
    per = {}
    for name, bucket in (metrics.get("per_attack_type") or {}).items():
        per[name] = {
            "n": bucket.get("n"),
            "catch_rate": bucket.get("catch_rate"),
            "false_blocks": bucket.get("false_blocks"),
            "false_block_rate": bucket.get("false_block_rate"),
            "evidence_quote_match": bucket.get("evidence_quote_match"),
        }
    return {
        "n": metrics.get("n"),
        "catch_rate": metrics.get("catch_rate"),
        "false_block_rate_clean": metrics.get("false_block_rate_clean"),
        "evidence_quote_match": metrics.get("evidence_quote_match"),
        "per_attack_type": per,
    }


def _normalize_pred(pred: dict) -> dict:
    out = dict(pred)
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


def score_rows(rows: list[LabelRow], predict) -> dict:
    preds = [_normalize_pred(predict(row)) for row in rows]
    return score_predictions(rows, preds)


def _remembering(predict):
    """Call the model once per page id. Replay and the round report share the answers."""
    seen: dict[str, dict] = {}

    def wrapped(row: LabelRow) -> dict:
        key = row.page_id or id(row)
        if key not in seen:
            seen[key] = predict(row)
        return seen[key]

    return wrapped


def pending_evals(
    *,
    train_rows: list[LabelRow],
    dev_rows: list[LabelRow],
    sample_ids: list[str],
    testset_labels: str | None,
    slice_file: str | None,
    content_hash: str | None,
) -> dict:
    return {
        "status": "pending",
        "testset_content_hash": content_hash,
        "train_sample": {"n": len(sample_ids), "page_ids": sample_ids},
        "dev": {"n": len(dev_rows)},
        "testset": {"labels": testset_labels},
        "slice100": {"labels": slice_file},
        "train_dev_gap": None,
        "note": (
            "Scores are pending until python -m guardtrain round-eval. "
            "The next live round refuses to start without a scored dev eval. "
            "Misses for that round are the dev misses only."
        ),
    }


def _select(rows: list[LabelRow], ids: list[str]) -> list[LabelRow]:
    by_id = {row.page_id: row for row in rows}
    missing = [page_id for page_id in ids if page_id not in by_id]
    if missing:
        shown = ", ".join(missing[:8])
        raise ContractError(f"Train-sample page ids are not in the saved train split: {shown}")
    return [by_id[page_id] for page_id in ids]


def _slice_rows(rows: list[LabelRow], slice_file: Path | None) -> list[LabelRow]:
    if slice_file is None or not slice_file.is_file():
        return []
    wanted = set(load_id_list(slice_file))
    return [row for row in rows if row.page_id in wanted]


def write_dev_misses(path: Path, rows: list[LabelRow], metrics: dict) -> int:
    """Dev misses only. Test and slice misses are not written."""
    by_id = {row.page_id: row for row in rows}
    payload = []
    for page in metrics.get("pages") or []:
        if not page.get("miss"):
            continue
        row = by_id.get(page.get("page_id") or "")
        if row is None:
            continue
        raw = dict(row.as_dict())
        raw["page_set"] = "dev"
        raw["not_for_training"] = False
        raw["model_output"] = page.get("raw_output") or json.dumps(
            {
                "verdict": page.get("verdict"),
                "attack_type": page.get("attack_type"),
                "evidence": page.get("evidence") or "",
                "instruction": page.get("instruction") or "",
            },
            ensure_ascii=False,
        )
        payload.append(raw)
    write_jsonl(path, payload)
    return len(payload)


def _winner_trial(report: dict, round_index: int) -> str | None:
    if report.get("base_eval"):
        return None
    winner = report.get("winner")
    if isinstance(winner, str) and winner:
        return winner
    if report.get("trials"):
        return None
    if round_index == 0:
        return None
    return "sft"


def score_into_report(
    report: dict,
    *,
    train_rows: list[LabelRow],
    dev_rows: list[LabelRow],
    test_rows: list[LabelRow],
    slice_rows: list[LabelRow],
    predict,
    dev_miss_path: Path,
    content_hash: str | None,
    mix_rows: list[LabelRow] | None = None,
    spec_dirs: list[Path] | None = None,
    runs: Path | None = None,
    frozen_ids: set[str] | None = None,
) -> dict:
    """Fill ``report['evals']`` and write the dev miss file. Test misses are not saved.

    Also writes ``runs/r{N}/replay.jsonl`` and the pinned ``summary.json``.
    The headline test slice is ``heldout_template``. ``heldout_attack`` is recall only.
    """
    if not dev_rows:
        raise ContractError("Round eval needs the dev split. It was empty, so the train-dev gap cannot be scored.")
    if not test_rows:
        raise ContractError("Round eval needs the frozen test set.")
    predict = _remembering(predict)
    sample_ids = list((report.get("evals") or {}).get("train_sample", {}).get("page_ids") or [])
    if not sample_ids:
        sample_ids = [row.page_id for row in sample_train_rows(train_rows, min(64, len(train_rows)), report.get("round") or 0)]
    train_sample = _select(train_rows, sample_ids)
    planned_hash = (report.get("evals") or {}).get("testset_content_hash")
    train_metrics = score_rows(train_sample, predict)
    dev_metrics = score_rows(dev_rows, predict)
    test_metrics = score_rows(test_rows, predict)
    slice_summary = None
    if slice_rows:
        slice_summary = summarize_metrics(score_rows(slice_rows, predict))
    train_summary = summarize_metrics(train_metrics)
    train_summary["page_ids"] = sample_ids
    dev_summary = summarize_metrics(dev_metrics)
    n_misses = write_dev_misses(dev_miss_path, dev_rows, dev_metrics)
    changed = bool(planned_hash and content_hash and planned_hash != content_hash)
    dev_choice = trick_scores(dev_metrics)
    early = {
        "metric": EARLY_STOP_METRIC,
        "max_epochs": 2,
        "patience": 1,
        "dev_score": dev_choice["selection_score"],
        "epochs_run": (report.get("limits") or {}).get("epochs"),
    }
    history = report.get("epoch_dev_scores")
    if isinstance(history, list) and history:
        early.update(choose_stopped_epoch([float(score) for score in history]))
    round_index = int(report.get("round") or 0)
    log_runs = runs or dev_miss_path.parents[2]
    frozen = frozen_ids if frozen_ids is not None else discover_frozen_ids(repo_root())
    logs = write_round_logs(
        log_runs,
        round_index=round_index,
        train_rows=train_rows,
        dev_rows=dev_rows,
        test_rows=test_rows,
        predict=predict,
        winner_trial=_winner_trial(report, round_index),
        frozen_ids=frozen,
        mix_rows=mix_rows,
        spec_dirs=spec_dirs,
    )
    report["evals"] = {
        "status": "scored",
        "testset_content_hash": content_hash,
        "testset_hash_changed_since_train": changed,
        "headline_slice": HEADLINE_SLICE,
        "by_slice": logs["by_slice"],
        "train_sample": train_summary,
        "dev": dev_summary,
        "testset": summarize_metrics(test_metrics),
        "slice100": slice_summary,
        "train_dev_gap": train_dev_gap(train_summary, dev_summary),
        "dev_misses": {"path": str(dev_miss_path), "n": n_misses},
        "early_stopping": early,
        "replay": str(logs["replay_path"]),
        "summary": str(logs["summary_path"]),
        "winner_trial": logs["summary"]["winner_trial"],
        "note": (
            "train_dev_gap is train sample minus dev. A positive catch_rate means the "
            "pages the round trained on look easier than the held-out dev split. "
            "The next round may train on dev_misses only, never on test or slice misses. "
            "heldout_template is the headline test slice. heldout_attack is recall only."
        ),
    }
    return report


def dev_miss_path(runs: Path, round_index: int) -> Path:
    return runs / "training" / "datasets" / f"round{round_index}.dev.misses.jsonl"


def load_saved_split(path: Path) -> list[LabelRow]:
    from guardtrain.data import load_labels

    if not path.is_file():
        raise ContractError(f"Saved split is missing: {path}")
    return load_labels(path)
