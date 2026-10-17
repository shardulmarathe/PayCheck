"""Refuse a round whose pages contain a frozen test-pile string.

The check is ``gym.dataset.conflicts_with_test_pile``: the whole normalized
line, or a test-pile string of four or more words inside a longer line.
"""

from __future__ import annotations

import sys

from guardtrain.paths import repo_root
from guardtrain.schema import ContractError, LabelRow


def _conflicts():
    root = str(repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from gym.dataset import conflicts_with_test_pile
    except ImportError as exc:
        raise ContractError(
            "Refusing round: the gym overlap check is not importable. "
            "Run this from the guard-gym checkout so gym.dataset can be imported."
        ) from exc
    return conflicts_with_test_pile


def overlap_page_ids(rows: list[LabelRow]) -> list[str]:
    conflicts = _conflicts()
    hits: list[str] = []
    for row in rows:
        blobs = [row.page_text or "", row.evidence_text or "", row.instruction or ""]
        pieces: list[str] = []
        for blob in blobs:
            pieces.append(blob)
            pieces.extend(blob.splitlines())
        if any(piece.strip() and conflicts(piece) for piece in pieces):
            hits.append(row.page_id or "<missing page_id>")
    return hits


def assert_no_test_overlap(rows: list[LabelRow], *, what: str) -> None:
    hits = overlap_page_ids(rows)
    if not hits:
        return
    shown = ", ".join(hits[:8])
    extra = f" (+{len(hits) - 8} more)" if len(hits) > 8 else ""
    raise ContractError(
        f"Refusing round: {what} fails the gym overlap check. "
        f"{len(hits)} page(s) contain a frozen test-pile string: {shown}{extra}"
    )
