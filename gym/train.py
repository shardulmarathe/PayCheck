"""Round-0 training pages from the train split and fixed templates.

Held-out attacks (``copycat_domain``, ``listing_injection``) are not generated.
``fake_card_verification`` is generated. Dataset strings are taken only from
the train page ids, and any normalized test-pile string is dropped.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from gym.build import allocate, assert_rows_allowed, build_specs
from gym.dataset import conflicts_with_test_pile, load_rows, load_split, rows_for_ids, test_pile_keys
from gym.render import render_html
from gym.render_specs import walk_strings
from gym.hashing import content_hash
from gym.materialize import materialize
from gym.taxonomy import HELD_OUT, SPLIT_SEED


def training_specs(count: int, seed: int) -> list[dict]:
    if count < 1:
        raise SystemExit("--n must be at least 1")
    rows = load_rows()
    train_ids, _test_ids = load_split()
    plan = allocate(count)
    for attack, _variant, _kind, _n in plan:
        if attack in HELD_OUT:
            raise SystemExit(f"train plan included held-out attack {attack}")
    specs = build_specs(
        "train",
        plan,
        rows_for_ids(rows, train_ids),
        seed=seed,
        id_prefix=f"train-s{seed}",
    )
    assert_rows_allowed(specs, set(train_ids))
    banned = test_pile_keys()
    for spec in specs:
        if spec["trick"]["attack_type"] in HELD_OUT:
            raise SystemExit(f"held-out attack in {spec['page_id']}")
        for text in walk_strings(spec):
            if conflicts_with_test_pile(text, banned):
                raise SystemExit(f"{spec['page_id']} contains a test-pile string")
        if conflicts_with_test_pile(render_html(spec), banned):
            raise SystemExit(f"{spec['page_id']} renders a test-pile string")
    return specs


def write_training(count: int, out_dir: Path, seed: int) -> str:
    specs = training_specs(count, seed)
    labels = materialize(specs, out_dir)
    digest = content_hash(out_dir, slice_file=None)
    manifest = {
        "name": "checkout-guard-train-round0",
        "n": count,
        "seed": seed,
        "content_hash": digest,
        "held_out_excluded": sorted(HELD_OUT),
        "composition": dict(sorted(Counter(row["attack_type"] for row in labels).items())),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote train pages={len(labels)} dir={out_dir} hash={digest}")
    return digest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate round-0 labeled training pages.")
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SPLIT_SEED)
    args = parser.parse_args(argv)
    write_training(args.n, args.out, args.seed)


if __name__ == "__main__":
    main()
