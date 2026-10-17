"""Load the replay and tally JSON Schemas shipped with the package."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"


def _load(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


REPLAY_SCHEMA = _load("replay.json")
TALLY_SCHEMA = _load("tally.json")
