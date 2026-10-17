"""Round-0 training pages from the train split and fixed templates.

Held-out attacks (``copycat_domain``, ``listing_injection``) are not generated.
Dataset strings are taken only from ``gym/splits/train_page_ids.txt``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from gym.build import allocate, assert_rows_allowed, build_specs
from gym.dataset import load_rows, load_split, norm_ws, rows_for_ids
from gym.hashing import content_hash
from gym.materialize import materialize
from gym.taxonomy import HELD_OUT, SPLIT_SEED


def _banned_test_strings() -> list[str]:
    rows = load_rows()
    _train_ids, test_ids = load_split()
    banned = []
    for row in rows_for_ids(rows, test_ids):
        text = norm_ws(row["text"])
        if len(text) >= 40:
            banned.append(text)
    return banned


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
    banned = _banned_test_strings()
    for spec in specs:
        if spec["trick"]["attack_type"] in HELD_OUT:
            raise SystemExit(f"held-out attack in {spec['page_id']}")
        blob = json.dumps(spec, ensure_ascii=False)
        for text in banned:
            if text in blob:
                raise SystemExit(f"{spec['page_id']} contains a test-pile string")
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
