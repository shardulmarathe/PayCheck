import json
from pathlib import Path

import pytest

from gym.dataset import load_rows, load_split, norm_ws, rows_for_ids
from gym.render_specs import render_directory
from gym.taxonomy import HELD_OUT
from gym.train import training_specs, write_training
from gym.build import build_specs


def test_round0_excludes_held_out_attacks_and_test_strings(tmp_path: Path):
    specs = training_specs(8, seed=20261017)
    assert len(specs) == 8
    assert HELD_OUT.isdisjoint(spec["trick"]["attack_type"] for spec in specs)
    _train, test_ids = load_split()
    banned = [
        norm_ws(row["text"])
        for row in rows_for_ids(load_rows(), test_ids)
        if len(norm_ws(row["text"])) >= 40
    ]
    for spec in specs:
        blob = json.dumps(spec)
        assert not any(text in blob for text in banned)
        assert set(spec["dataset_page_ids"]).issubset(set(_train))
    digest = write_training(4, tmp_path / "train", seed=7)
    labels = (tmp_path / "train" / "labels.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(labels) == 4
    assert len(digest) == 64
    for line in labels:
        row = json.loads(line)
        assert row["attack_type"] not in HELD_OUT
        assert row["split"] == "train"


def test_attacker_renderer_rejects_held_out_and_test_strings(tmp_path: Path):
    rows = load_rows()
    train_ids, test_ids = load_split()
    good = build_specs(
        "train",
        [("hidden_fees", "drip", "checkout", 1)],
        rows_for_ids(rows, train_ids),
        seed=4,
        id_prefix="attacker",
    )[0]
    specs_dir = tmp_path / "specs"
    specs_dir.mkdir()
    (specs_dir / "good.json").write_text(json.dumps(good), encoding="utf-8")
    render_directory(specs_dir, tmp_path / "out", source="attacker-round1")
    label = json.loads((tmp_path / "out" / "labels.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert label["source"] == "attacker-round1"
    assert label["attack_type"] == "hidden_fees"
    assert label["bbox"] and len(label["bbox"]) == 4

    held = build_specs(
        "train",
        [("copycat_domain", "lookalike", "product", 1)],
        rows_for_ids(rows, train_ids),
        seed=4,
        id_prefix="held",
    )[0]
    held_dir = tmp_path / "held"
    held_dir.mkdir()
    (held_dir / "copycat.json").write_text(json.dumps(held), encoding="utf-8")
    with pytest.raises(SystemExit):
        render_directory(held_dir, tmp_path / "held-out")

    leaked = json.loads(json.dumps(good))
    leaked["page_id"] = "attacker-leaked"
    banned = next(
        norm_ws(row["text"])
        for row in rows_for_ids(rows, test_ids)
        if row["label"] == "0" and len(norm_ws(row["text"])) >= 40
    )
    leaked["page"]["product"]["description"] = banned
    leak_dir = tmp_path / "leak"
    leak_dir.mkdir()
    (leak_dir / "leak.json").write_text(json.dumps(leaked), encoding="utf-8")
    with pytest.raises(SystemExit):
        render_directory(leak_dir, tmp_path / "leak-out")
