"""Training rounds from the train split and a generated catalog.

Each round gets its own stores, products, prices, fees, add-ons, and wording.
Held-out attacks (``copycat_domain``, ``listing_injection``) are not generated.
About 15% of the generated pages are written to ``<out>/dev/`` and are not part
of the training labels. The frozen test set is never used as that holdout.

Rounds 2 and later also overlap-check attacker specs in ``data/attacker-roundN``
when that directory is present. Any overlap fails the round.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from gym.build import allocate, assert_rows_allowed, build_specs
from gym.catalog import generate_catalog, seed_for_round
from gym.dataset import load_rows, load_split, rows_for_ids
from gym.hashing import content_hash
from gym.materialize import materialize
from gym.overlap import assert_no_test_overlap
from gym.paths import ROOT
from gym.taxonomy import HELD_OUT
from gym.validate import validate_spec


def training_specs(count: int, seed: int, *, round_n: int = 1) -> list[dict]:
    if count < 1:
        raise SystemExit("--n must be at least 1")
    if round_n < 1:
        raise SystemExit("--round starts at 1")
    rows = load_rows()
    train_ids, _test_ids = load_split()
    plan = allocate(count)
    for attack, _variant, _kind, _n in plan:
        if attack in HELD_OUT:
            raise SystemExit(f"train plan included held-out attack {attack}")
    catalog = generate_catalog(seed, round_n=round_n)
    specs = build_specs(
        "train",
        plan,
        rows_for_ids(rows, train_ids),
        seed=seed,
        id_prefix=f"r{round_n}",
        round_n=round_n,
        catalog=catalog,
    )
    assert_rows_allowed(specs, set(train_ids))
    for spec in specs:
        validate_spec(spec)
        if spec["trick"]["attack_type"] in HELD_OUT:
            raise SystemExit(f"held-out attack in {spec['page_id']}")
    assert_no_test_overlap(specs, label=f"round {round_n}")
    return specs


def split_train_dev(specs: list[dict], percent: int = 15) -> tuple[list[dict], list[dict]]:
    """Hold out ``percent`` of the generated pages, stratified by attack type.

    The dev pages are a subset of this round. They are not the frozen test set.
    """
    if percent < 0 or percent > 50:
        raise ValueError("dev percent must be between 0 and 50")
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for spec in specs:
        attack = spec["trick"]["attack_type"]
        if attack not in groups:
            groups[attack] = []
            order.append(attack)
        groups[attack].append(spec)
    total = len(specs)
    dev_n = (total * percent) // 100
    if dev_n <= 0 or total < 2:
        return list(specs), []
    if dev_n >= total:
        dev_n = total - 1
    raw = {attack: dev_n * len(groups[attack]) / total for attack in order}
    floors = {attack: int(raw[attack]) for attack in order}
    leftover = dev_n - sum(floors.values())
    ranked = sorted(order, key=lambda attack: (-(raw[attack] - floors[attack]), order.index(attack)))
    counts = dict(floors)
    cursor = 0
    while leftover > 0 and ranked:
        attack = ranked[cursor % len(ranked)]
        if counts[attack] < len(groups[attack]):
            counts[attack] += 1
            leftover -= 1
        cursor += 1
        if cursor > len(ranked) * (dev_n + 2):
            break
    dev_ids: set[str] = set()
    for attack, group in groups.items():
        take = counts[attack]
        if take <= 0:
            continue
        if take >= len(group):
            take = len(group) - 1 if len(group) > 1 else 0
        for index in range(take):
            dev_ids.add(group[int(index * len(group) / take)]["page_id"])
    dev = [spec for spec in specs if spec["page_id"] in dev_ids]
    train = [spec for spec in specs if spec["page_id"] not in dev_ids]
    return train, dev


def _attacker_paths(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    paths = [
        path
        for path in sorted(directory.glob("*.json"))
        if path.name not in {"manifest.json", "catalog.json"}
    ]
    specs_dir = directory / "specs"
    if specs_dir.is_dir():
        paths.extend(sorted(specs_dir.glob("*.json")))
    return paths


def load_attacker_specs(directory: Path) -> list[dict]:
    """Load attacker specs and refuse held-out attacks or test-set overlap."""
    paths = _attacker_paths(directory)
    if not paths:
        return []
    specs = []
    for path in paths:
        spec = json.loads(path.read_text(encoding="utf-8"))
        validate_spec(spec)
        attack = spec["trick"]["attack_type"]
        if attack in HELD_OUT:
            raise SystemExit(
                f"{path.name}: {attack} is held out of training. "
                "Do not put it in a training round."
            )
        if spec.get("split") != "train":
            raise SystemExit(f"{path.name}: attacker specs for a training round must be split train")
        specs.append(spec)
    assert_no_test_overlap(specs, label=f"attacker specs in {directory}")
    return specs


def _write_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_training(
    count: int,
    out_dir: Path,
    seed: int,
    *,
    round_n: int = 1,
    attacker_dir: Path | None = None,
    attacker_explicit: bool = False,
    dev_percent: int = 15,
) -> str:
    specs = training_specs(count, seed, round_n=round_n)
    catalog = generate_catalog(seed, round_n=round_n)
    attacker_note = "not-checked"
    attacker_specs: list[dict] = []
    if attacker_explicit:
        if attacker_dir is None or not attacker_dir.exists():
            raise SystemExit(f"attacker spec directory not found: {attacker_dir}")
        attacker_specs = load_attacker_specs(attacker_dir)
        attacker_note = str(attacker_dir)
    elif round_n >= 2:
        default_dir = ROOT / "data" / f"attacker-round{round_n}"
        if default_dir.exists():
            attacker_specs = load_attacker_specs(default_dir)
            attacker_note = str(default_dir)
        else:
            print(f"no attacker specs at {default_dir} (round {round_n} template pages only)")
            attacker_note = "missing"
    train_specs, dev_specs = split_train_dev(specs, dev_percent)
    labels = materialize(train_specs, out_dir)
    digest = content_hash(out_dir, slice_file=None)
    dev_digest = None
    if dev_specs:
        dev_labels = materialize(dev_specs, out_dir / "dev")
        dev_digest = content_hash(out_dir / "dev", slice_file=None)
        _write_manifest(
            out_dir / "dev" / "manifest.json",
            {
                "role": "dev",
                "round": round_n,
                "n": len(dev_labels),
                "seed": seed,
                "content_hash": dev_digest,
                "note": (
                    "Holdout from this round for misses and overfitting. "
                    "Do not train on these pages. Do not pick misses from the frozen test set."
                ),
                "composition": dict(sorted(Counter(row["attack_type"] for row in dev_labels).items())),
            },
        )
    attacker_digest = None
    if attacker_specs:
        attacker_labels = materialize(attacker_specs, out_dir / "attacker")
        attacker_digest = content_hash(out_dir / "attacker", slice_file=None)
        _write_manifest(
            out_dir / "attacker" / "manifest.json",
            {
                "role": "attacker",
                "round": round_n,
                "n": len(attacker_labels),
                "content_hash": attacker_digest,
                "overlap_check": "pass",
            },
        )
    manifest = {
        "name": f"checkout-guard-train-round{round_n}",
        "round": round_n,
        "n_generated": count,
        "n_train": len(labels),
        "n_dev": len(dev_specs),
        "dev_percent": dev_percent,
        "seed": seed,
        "seed_formula": "SPLIT_SEED + round * 1000003",
        "content_hash": digest,
        "dev_content_hash": dev_digest,
        "attacker_content_hash": attacker_digest,
        "attacker_dir": attacker_note,
        "attacker_pages": len(attacker_specs),
        "overlap_check": "pass",
        "held_out_excluded": sorted(HELD_OUT),
        "composition": dict(sorted(Counter(row["attack_type"] for row in labels).items())),
        "catalog": _catalog_summary(catalog),
        "note": (
            "Train on labels.jsonl in this directory only. "
            "dev/ is the round holdout and is not for training. "
            "The frozen test set is not a dev set."
        ),
    }
    _write_manifest(out_dir / "manifest.json", manifest)
    print(
        f"wrote round={round_n} train={len(labels)} dev={len(dev_specs)} "
        f"attacker={len(attacker_specs)} dir={out_dir} hash={digest} overlap=pass seed={seed}"
    )
    return digest


def _catalog_summary(catalog) -> dict:
    return {
        "layout": (catalog.presentation or {}).get("layout", "summary-right"),
        "ship_line": catalog.ship_line,
        "subscribe": catalog.subscribe_template,
        "stores": [
            {"id": store["id"], "brand": store["brand"], "domain": store["domain"]}
            for store in catalog.stores
        ],
        "products": [
            {"name": product["name"], "price_cents": product["price_cents"]}
            for group in catalog.products.values()
            for product in group
        ],
        "fees": [{"name": name, "amount_cents": cents} for name, cents in catalog.fees],
        "addons": [
            {"name": name, "price_cents": cents} for name, _sku, cents in catalog.addons
        ],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one training round. The seed defaults to SPLIT_SEED + round * 1000003."
    )
    parser.add_argument("--round", type=int, default=1, help="Round number, starting at 1.")
    parser.add_argument("--n", type=int, default=50, help="Pages to generate before the dev holdout.")
    parser.add_argument("--out", type=Path, default=None, help="Defaults to data/trainset/roundN.")
    parser.add_argument("--seed", type=int, default=None, help="Defaults to the seed derived from --round.")
    parser.add_argument(
        "--attacker",
        type=Path,
        default=None,
        help="Attacker spec directory. Rounds 2+ also read data/attacker-roundN when it exists.",
    )
    parser.add_argument("--dev-percent", type=int, default=15)
    args = parser.parse_args(argv)
    if args.round < 1:
        raise SystemExit("--round starts at 1")
    if args.n < 1:
        raise SystemExit("--n must be at least 1")
    if args.seed is None:
        args.seed = seed_for_round(args.round)
    if args.out is None:
        args.out = ROOT / "data" / "trainset" / f"round{args.round}"
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    write_training(
        args.n,
        args.out,
        args.seed,
        round_n=args.round,
        attacker_dir=args.attacker,
        attacker_explicit=args.attacker is not None,
        dev_percent=args.dev_percent,
    )


if __name__ == "__main__":
    main()
