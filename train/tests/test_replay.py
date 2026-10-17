"""Pinned replay.jsonl and summary.json schema. Test page ids never enter the replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from guardtrain.data import discover_frozen_ids
from guardtrain.early_stop import choose_stopped_epoch, clamp_epochs
from guardtrain.paths import repo_root
from guardtrain.replay import REPLAY_KEYS, SCORE_KEYS, SUMMARY_KEYS, TEST_SLICE_ORDER, write_round_logs
from guardtrain.schema import ContractError, LabelRow


def _row(
    page_id: str,
    *,
    verdict: str,
    attack: str,
    family: str,
    split: str,
    kind: str,
    mix_source: str = "train",
    slice_name: str = "",
) -> LabelRow:
    return LabelRow(
        page_id=page_id,
        store="Northmart",
        family=family,
        attack_type=attack,
        verdict=verdict,
        split=split,
        page_text=f"kind: {kind}\nOrder total $10.\n",
        mix_source=mix_source,
        extra={"page_kind": kind, **({"slice": slice_name} if slice_name else {})},
    )


def _predict(row: LabelRow) -> dict:
    table = {
        "p-a11ce001": ("block", "hidden_fees"),
        "p-a11ce002": ("pass", "none"),
        "p-a11ce004": ("pass", "none"),
        "p-a11ce003": ("pass", "none"),
        "p-a11ce005": ("pass", "none"),
        "p-b10c0001": ("block", "hidden_fees"),
        "p-b10c0002": ("pass", "none"),
        "p-b10c0003": ("pass", "none"),
        "p-b10c0004": ("pass", "none"),
        "p-b10c0005": ("block", "copycat_domain"),
        "p-b10c0006": ("pass", "none"),
    }
    verdict, attack = table[row.page_id]
    return {
        "verdict": verdict,
        "attack_type": attack,
        "evidence": "",
        "instruction": "",
        "parse_ok": True,
        "latency_ms": 0,
        "cost_usd": "0",
        "input_tokens": 0,
        "output_tokens": 0,
        "raw": "",
    }


def test_summary_schema_and_replay_hides_test_ids(tmp_path: Path) -> None:
    frozen = discover_frozen_ids(repo_root())
    assert frozen, "frozen test ids are read from the checkout, not hardcoded"
    used = {
        "p-a11ce001",
        "p-a11ce002",
        "p-a11ce003",
        "p-a11ce004",
        "p-a11ce005",
        "p-b10c0001",
        "p-b10c0002",
        "p-b10c0003",
        "p-b10c0004",
        "p-b10c0005",
        "p-b10c0006",
    }
    assert used.isdisjoint(frozen)

    train_rows = [
        _row("p-a11ce001", verdict="block", attack="hidden_fees", family="upsell", split="train", kind="checkout"),
        _row(
            "p-a11ce002",
            verdict="block",
            attack="price_change",
            family="upsell",
            split="train",
            kind="product",
            mix_source="miss",
        ),
        _row("p-a11ce004", verdict="pass", attack="none", family="clean", split="train", kind="payment"),
    ]
    dev_rows = [
        _row("p-a11ce003", verdict="block", attack="preselected_addon", family="upsell", split="dev", kind="cart"),
        _row("p-a11ce005", verdict="pass", attack="none", family="clean", split="dev", kind="checkout"),
    ]
    test_rows = [
        _row("p-b10c0001", verdict="block", attack="hidden_fees", family="upsell", split="test", kind="checkout", slice_name="in_dist"),
        _row("p-b10c0002", verdict="pass", attack="none", family="clean", split="test", kind="cart", slice_name="in_dist"),
        _row(
            "p-b10c0003",
            verdict="block",
            attack="subscription_trap",
            family="upsell",
            split="test",
            kind="checkout",
            slice_name="heldout_template",
        ),
        _row(
            "p-b10c0004",
            verdict="pass",
            attack="none",
            family="clean",
            split="test",
            kind="product",
            slice_name="heldout_template",
        ),
        _row(
            "p-b10c0005",
            verdict="block",
            attack="copycat_domain",
            family="scam",
            split="test",
            kind="product",
            slice_name="heldout_attack",
        ),
        _row(
            "p-b10c0006",
            verdict="block",
            attack="listing_injection",
            family="scam",
            split="test",
            kind="product",
            slice_name="heldout_attack",
        ),
    ]
    logs = write_round_logs(
        tmp_path,
        round_index=1,
        train_rows=train_rows,
        dev_rows=dev_rows,
        test_rows=test_rows,
        predict=_predict,
        winner_trial="lr1e-04-r16",
        frozen_ids=frozen,
    )
    summary = json.loads((tmp_path / "r1" / "summary.json").read_text(encoding="utf-8"))
    assert list(summary) == list(SUMMARY_KEYS)
    assert summary["round"] == 1
    assert summary["winner_trial"] == "lr1e-04-r16"
    assert summary["new_pages"] == 4
    assert summary["seeded_from_misses"] == 1
    for name in ("train", "dev"):
        assert list(summary[name]) == list(SCORE_KEYS)
    assert list(summary["test"]) == list(TEST_SLICE_ORDER)
    for name in TEST_SLICE_ORDER:
        assert list(summary["test"][name]) == list(SCORE_KEYS)
    assert summary["test"]["heldout_attack"]["false_block_rate"] is None
    assert summary["test"]["heldout_attack"]["n"] == 2
    assert summary["test"]["in_dist"]["f1"] == pytest.approx(1.0)
    assert summary["test"]["heldout_template"]["f1"] == pytest.approx(0.0)
    assert summary["in_dist_vs_heldout_template_gap"] == pytest.approx(
        summary["test"]["in_dist"]["f1"] - summary["test"]["heldout_template"]["f1"]
    )
    assert summary["in_dist_vs_heldout_template_gap"] == pytest.approx(1.0)
    assert logs["by_slice"]["heldout_attack"]["primary"] == "recall"
    assert logs["headline_slice"] == "heldout_template"
    assert list(logs["by_slice"])[0] == "heldout_template"

    replay_path = tmp_path / "r1" / "replay.jsonl"
    lines = [json.loads(line) for line in replay_path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 5
    replay_ids = set()
    for line in lines:
        assert list(line) == list(REPLAY_KEYS)
        assert isinstance(line["round"], int) and not isinstance(line["round"], bool)
        assert isinstance(line["correct"], bool)
        assert isinstance(line["fed_back"], bool)
        assert line["source"] in {"fresh", "from_miss"}
        assert line["split"] in {"train", "dev"}
        assert line["page_id"].startswith("p-")
        replay_ids.add(line["page_id"])
    assert replay_ids.isdisjoint(frozen)
    assert replay_ids.isdisjoint({row.page_id for row in test_rows})
    by_id = {line["page_id"]: line for line in lines}
    miss = by_id["p-a11ce002"]
    assert miss["source"] == "from_miss"
    assert miss["fed_back"] is False
    assert miss["split"] == "train"
    dev_miss = by_id["p-a11ce003"]
    assert dev_miss == {
        "round": 1,
        "page_id": "p-a11ce003",
        "store": "Northmart",
        "page_kind": "cart",
        "trick": "preselected_addon",
        "split": "dev",
        "label": "block",
        "verdict": "pass",
        "correct": False,
        "fed_back": True,
        "source": "fresh",
    }

    leaked = _row(
        sorted(frozen)[0],
        verdict="block",
        attack="hidden_fees",
        family="upsell",
        split="train",
        kind="checkout",
    )
    with pytest.raises(ContractError, match="replay.jsonl"):
        write_round_logs(
            tmp_path / "leak",
            round_index=1,
            train_rows=[leaked],
            dev_rows=dev_rows,
            test_rows=test_rows,
            predict=_predict,
            winner_trial="lr1e-04-r16",
            frozen_ids=frozen,
        )
    assert not (tmp_path / "leak" / "r1" / "replay.jsonl").exists()


def test_round0_summary_has_no_winner(tmp_path: Path) -> None:
    frozen = discover_frozen_ids(repo_root())
    train_rows = [
        _row("p-a11ce001", verdict="block", attack="hidden_fees", family="upsell", split="train", kind="checkout"),
    ]
    dev_rows = [
        _row("p-a11ce005", verdict="pass", attack="none", family="clean", split="dev", kind="payment"),
    ]
    logs = write_round_logs(
        tmp_path,
        round_index=0,
        train_rows=train_rows,
        dev_rows=dev_rows,
        test_rows=[],
        predict=_predict,
        winner_trial=None,
        frozen_ids=frozen,
    )
    summary = logs["summary"]
    assert list(summary) == list(SUMMARY_KEYS)
    assert summary["round"] == 0
    assert summary["winner_trial"] is None
    assert summary["new_pages"] == 2
    assert summary["seeded_from_misses"] == 0
    assert summary["test"]["heldout_attack"]["false_block_rate"] is None
    assert summary["test"]["heldout_attack"]["n"] == 0
    assert all(line["round"] == 0 for line in logs["lines"])


def test_epochs_cap_at_two_and_stop_on_dev_f1() -> None:
    assert clamp_epochs(1) == 1
    assert clamp_epochs(2) == 2
    with pytest.raises(ContractError, match="1 or 2"):
        clamp_epochs(3)
    improved = choose_stopped_epoch([0.2, 0.5])
    assert improved["best_epoch"] == 2
    assert improved["stopped_early"] is False
    assert improved["metric"] == "trick_f1 - false_block_rate_clean"
    stalled = choose_stopped_epoch([0.4, 0.3])
    assert stalled["best_epoch"] == 1
    assert stalled["stopped_early"] is True
    assert stalled["epochs_considered"] == 2
