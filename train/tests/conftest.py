"""Skip tests that need the locked test set when it is absent.

The locked test set (``data/testset/``, ``gym/testset/``, and
``gym/splits/test_page_ids.txt``) is held back from the public repository on
purpose. These tests read it, so they skip instead of failing without it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LOCKED_PRESENT = (REPO / "data/testset/labels.jsonl").exists() and (
    REPO / "gym/splits/test_page_ids.txt"
).exists()

NEEDS_LOCKED_TEST_SET = {
    "test_prompt_hides_ids_and_label_words_on_real_pages",
    "test_round_dry_run_orders_commands_and_refuses_the_cap",
    "test_round_live_fake_settles_actual_cost",
    "test_create_failure_releases_the_reservation",
    "test_poll_retries_then_cancels_and_download_is_after_settle",
    "test_prepare_round_keeps_groups_apart_and_logs_structure",
    "test_summary_schema_and_replay_hides_test_ids",
}


def pytest_collection_modifyitems(config, items):
    if LOCKED_PRESENT:
        return
    skip = pytest.mark.skip(reason="needs the locked test set, which is held back from this repo")
    for item in items:
        if item.originalname in NEEDS_LOCKED_TEST_SET or item.name in NEEDS_LOCKED_TEST_SET:
            item.add_marker(skip)
