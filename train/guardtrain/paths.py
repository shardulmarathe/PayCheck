"""Repository paths. Editable installs keep this file inside the checkout."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("GUARD_REPO_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    candidates = []
    if len(here.parents) > 2:
        candidates.append(here.parents[2])
    candidates.append(Path.cwd())
    for cand in candidates:
        if (cand / "train" / "guardtrain").is_dir():
            return cand
    return Path.cwd()


def runs_dir() -> Path:
    env = os.environ.get("GUARD_RUNS_DIR")
    if env:
        return Path(env).resolve()
    return repo_root() / "runs"
