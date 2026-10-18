"""Pick a sweep winner from the dev split only.

The score is the F1 of the block class (tricks) minus the false-block rate on
clean pages. A model that blocks every clean page cannot win on F1 alone.
The frozen test set is not an input to this choice.
"""

from __future__ import annotations


def trick_scores(metrics: dict) -> dict:
    tp = 0
    fp = 0
    fn = 0
    n_clean = 0
    for page in metrics.get("pages") or []:
        gold_block = page.get("gold_verdict") == "block"
        pred_block = page.get("verdict") == "block"
        if gold_block and pred_block:
            tp += 1
        elif gold_block:
            fn += 1
        if page.get("family") == "clean":
            n_clean += 1
            if pred_block:
                fp += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    false_block_rate = (fp / n_clean) if n_clean else 0.0
    return {
        "trick_f1": f1,
        "trick_precision": precision,
        "trick_recall": recall,
        "false_block_rate_clean": false_block_rate,
        "selection_score": f1 - false_block_rate,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "n_clean": n_clean,
    }


def pick_winner(trials: list[dict]) -> str | None:
    """Highest dev selection score. Ties prefer fewer clean false blocks, then the name."""
    scored = [trial for trial in trials if trial.get("selection_score") is not None]
    if not scored:
        return None
    scored.sort(
        key=lambda trial: (
            -float(trial["selection_score"]),
            float(trial.get("false_block_rate_clean") or 0),
            -float(trial.get("trick_f1") or 0),
            str(trial.get("name") or ""),
        )
    )
    return str(scored[0]["name"])
