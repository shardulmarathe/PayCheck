"""Nearest-neighbor character similarity between test slices and a train round.

The score is the normalized indel ratio used by ``rapidfuzz.fuzz.ratio``:
``1 - indel_distance / (len(a) + len(b))``. Each page is rendered HTML with
every URL removed. The recorded value for a test page is its nearest train page.
"""

from __future__ import annotations

import re

_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def strip_urls(text: str) -> str:
    return _URL.sub("", text or "")


def nearest_ratios(queries: list[str], corpus: list[str]) -> list[float]:
    """Max character similarity of each query against the corpus, in ``[0, 1]``."""
    if not corpus:
        raise ValueError("train corpus is empty")
    from rapidfuzz import fuzz, process

    ratios: list[float] = []
    for index, query in enumerate(queries):
        match = process.extractOne(query, corpus, scorer=fuzz.ratio)
        if match is None:
            raise RuntimeError("nearest neighbor search returned nothing")
        ratios.append(match[1] / 100.0)
        if index and index % 50 == 0:
            print(f"similarity {index}/{len(queries)}", flush=True)
    return ratios


def summarize(scores: list[float]) -> dict[str, float | int]:
    if not scores:
        return {"n": 0, "mean": 0.0, "max": 0.0}
    return {
        "n": len(scores),
        "mean": round(sum(scores) / len(scores), 4),
        "max": round(max(scores), 4),
    }
