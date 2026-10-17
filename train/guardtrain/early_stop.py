"""Epoch cap and the dev stop metric.

Veri's managed ``sft_text`` job does not score the dev split while it trains,
so the launched job is capped at two epochs. When per-epoch dev scores are
available, the epoch to keep is the one with the best
``trick_f1 - false_block_rate_clean``. A later epoch that does not beat that
score is not used.
"""

from __future__ import annotations

from guardtrain.schema import MAX_EPOCHS, ContractError

EARLY_STOP_METRIC = "trick_f1 - false_block_rate_clean"
PATIENCE = 1


def clamp_epochs(epochs: int) -> int:
    """Allow 1 or 2 epochs. Anything else is refused."""
    if isinstance(epochs, bool) or not isinstance(epochs, int) or epochs < 1 or epochs > MAX_EPOCHS:
        raise ContractError(
            "Training epochs must be 1 or 2. "
            "Early stopping uses dev trick_f1 minus the false-block rate, "
            f"and the job is capped at {MAX_EPOCHS} epochs."
        )
    return epochs


def choose_stopped_epoch(
    scores: list[float],
    *,
    patience: int = PATIENCE,
    max_epochs: int = MAX_EPOCHS,
) -> dict:
    """Pick the epoch to keep from dev selection scores, one per finished epoch.

    ``scores[i]`` is ``trick_f1 - false_block_rate_clean`` after epoch ``i + 1``.
    Stop once a later epoch fails to beat the best so far for ``patience`` epochs.
    """
    if max_epochs < 1:
        raise ContractError("max_epochs must be at least 1")
    limited = [float(score) for score in scores[:max_epochs]]
    if not limited:
        return {
            "metric": EARLY_STOP_METRIC,
            "max_epochs": max_epochs,
            "patience": patience,
            "best_epoch": None,
            "best_score": None,
            "epochs_considered": 0,
            "stopped_early": False,
        }
    best_index = 0
    best_score = limited[0]
    last_index = 0
    misses = 0
    stopped_early = False
    for index, score in enumerate(limited):
        last_index = index
        if index == 0 or score > best_score:
            best_score = score
            best_index = index
            misses = 0
            continue
        misses += 1
        if misses >= patience:
            stopped_early = True
            break
    return {
        "metric": EARLY_STOP_METRIC,
        "max_epochs": max_epochs,
        "patience": patience,
        "best_epoch": best_index + 1,
        "best_score": best_score,
        "epochs_considered": last_index + 1,
        "stopped_early": stopped_early,
    }
