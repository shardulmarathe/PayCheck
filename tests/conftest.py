"""Shared pytest hooks.

The locked test set (``data/testset/``, ``gym/testset/``, and
``gym/splits/test_page_ids.txt``) is held back from the public repository on
purpose. Tests that read it are skipped, not failed, when it is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCKED_PATHS = ("data/testset", "gym/testset/", "gym/splits/test_page_ids.txt")
LOCKED_PRESENT = (ROOT / "data/testset/labels.jsonl").exists() and (
    ROOT / "gym/splits/test_page_ids.txt"
).exists()


def _locked_missing(exc: BaseException) -> bool:
    if not isinstance(exc, FileNotFoundError):
        return False
    name = str(getattr(exc, "filename", "") or exc).replace("\\", "/")
    return any(part in name for part in LOCKED_PATHS)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    outcome = yield
    if LOCKED_PRESENT or outcome.excinfo is None:
        return
    exc = outcome.excinfo[1]
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if _locked_missing(exc):
            outcome.force_exception(
                pytest.skip.Exception("needs the locked test set, which is held back from this repo")
            )
            return
        exc = exc.__cause__ or exc.__context__
