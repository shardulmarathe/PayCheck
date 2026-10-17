"""Training rounds from the train split and a generated catalog.

Each round gets its own stores, products, prices, fees, add-ons, and wording.
Held-out attacks (``copycat_domain``, ``listing_injection``) are not generated.
``--n-train`` pages are the training labels. ``--n-dev`` pages are a holdout
taken as whole ``group_id`` families and written to ``<out>/dev/``. The frozen
test set is never used as that holdout.

Rounds 2 and later also overlap-check attacker specs in ``data/attacker-roundN``
when that directory is present. Any overlap fails the round.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from gym.build import allocate, assert_rows_allowed, build_specs
from gym.catalog import generate_catalog, seed_for_round
from gym.dataset import load_rows, load_split, rows_for_ids
from gym.hashing import content_hash
from gym.materialize import materialize
from gym.overlap import assert_no_test_overlap
from gym.paths import ROOT
from gym.render import render_html, structural_features
from gym.taxonomy import HELD_OUT
from gym.validate import validate_spec
from gym.wording import diversity


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


def _strata(specs: list[dict]) -> list[tuple[tuple[str, str, str], list[dict]]]:
    buckets: dict[tuple[str, str, str], list[dict]] = {}
    order: list[tuple[str, str, str]] = []
    for spec in specs:
        key = (
            spec["trick"]["attack_type"],
            spec["trick"]["variant"],
            spec["page"]["kind"],
        )
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(spec)
    return [(key, buckets[key]) for key in order]


def _dev_targets(sizes: list[int], n_dev: int) -> list[int]:
    total = sum(sizes)
    if n_dev <= 0 or total == 0:
        return [0] * len(sizes)
    if n_dev > total:
        raise ValueError(f"dev count {n_dev} is larger than the round ({total})")
    raw = [n_dev * size / total for size in sizes]
    floors = [int(value) for value in raw]
    leftover = n_dev - sum(floors)
    order = sorted(range(len(sizes)), key=lambda index: (-(raw[index] - floors[index]), index))
    counts = floors[:]
    for index in order:
        if leftover <= 0:
            break
        if counts[index] < sizes[index]:
            counts[index] += 1
            leftover -= 1
    if sum(counts) != n_dev:
        raise RuntimeError("dev allocation does not match n_dev")
    return counts


def _group_size(size: int, want: int) -> int:
    """Family size that divides both the stratum and the dev quota.

    Consecutive seeds in one stratum share a family. The size stays at most 8
    so a family is a short seed window. A size of 1 is still a whole group.
    """
    if size <= 1:
        return 1
    if want <= 0 or want >= size:
        return min(8, size)
    common = math.gcd(size, want)
    cap = min(8, common)
    for candidate in range(cap, 0, -1):
        if common % candidate == 0:
            return candidate
    return 1


def _chunk_indexes(n_groups: int, take: int) -> set[int]:
    if take <= 0:
        return set()
    if take >= n_groups:
        return set(range(n_groups))
    step = n_groups / take
    picked = {int(index * step) for index in range(take)}
    if len(picked) != take:
        picked = set(range(take))
    return picked


def split_train_dev(
    specs: list[dict],
    percent: int = 15,
    n_dev: int | None = None,
) -> tuple[list[dict], list[dict]]:
    """Hold out whole seed families.

    ``n_dev`` is an exact page count. When it is omitted, ``percent`` of the
    generated pages are held out (the older ``--n`` path). A ``group_id`` is
    entirely train or entirely dev. Dev specs are marked ``split: dev``.
    """
    if n_dev is None:
        if percent < 0 or percent > 50:
            raise ValueError("dev percent must be between 0 and 50")
        n_dev = (len(specs) * percent) // 100
    if n_dev < 0:
        raise ValueError("n_dev must be at least 0")
    strata = _strata(specs)
    targets = _dev_targets([len(rows) for _key, rows in strata], n_dev)
    next_id = 1
    for (_key, rows), want in zip(strata, targets):
        size = _group_size(len(rows), want)
        chunks = [rows[index : index + size] for index in range(0, len(rows), size)]
        if want <= 0:
            take = 0
        elif want >= len(rows):
            take = len(chunks)
        else:
            take = want // size
        picked = _chunk_indexes(len(chunks), take)
        for index, chunk in enumerate(chunks):
            group_id = f"g-{next_id:04d}"
            next_id += 1
            for spec in chunk:
                spec["group_id"] = group_id
                spec["split"] = "dev" if index in picked else "train"
    dev = [spec for spec in specs if spec["split"] == "dev"]
    train = [spec for spec in specs if spec["split"] != "dev"]
    if len(dev) != n_dev:
        raise RuntimeError(f"dev split has {len(dev)} pages, wanted {n_dev}")
    train_groups = {spec["group_id"] for spec in train}
    dev_groups = {spec["group_id"] for spec in dev}
    if train_groups & dev_groups:
        raise RuntimeError("a group_id is in both train and dev")
    return train, dev


_FEATURES = ("checkbox", "popup", "fee", "strike", "radio")


def feature_rates(specs: list[dict]) -> dict:
    """Clean rate divided by the trick rate for each structural control."""
    clean = [spec for spec in specs if spec["trick"]["attack_type"] == "none"]
    trick = [spec for spec in specs if spec["trick"]["attack_type"] != "none"]

    def rates(group: list[dict]) -> dict[str, float]:
        hits: Counter[str] = Counter()
        for spec in group:
            found = structural_features(render_html(spec))
            for name in _FEATURES:
                if found[name]:
                    hits[name] += 1
        total = len(group) or 1
        return {name: round(hits[name] / total, 4) for name in _FEATURES}

    clean_rates = rates(clean)
    trick_rates = rates(trick)
    relative = {}
    for name in _FEATURES:
        if trick_rates[name] == 0:
            relative[name] = None
        else:
            relative[name] = round(clean_rates[name] / trick_rates[name], 4)
    return {
        "clean": clean_rates,
        "trick": trick_rates,
        "relative": relative,
        "n_clean": len(clean),
        "n_trick": len(trick),
    }


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
    n_dev: int | None = None,
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
    train_specs, dev_specs = split_train_dev(specs, dev_percent, n_dev=n_dev)
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
        "dev_percent": dev_percent if n_dev is None else None,
        "diversity_train": diversity(train_specs),
        "diversity_dev": diversity(dev_specs),
        "feature_rates": feature_rates(specs),
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
    train_diversity = diversity(train_specs)
    print(
        f"wrote round={round_n} train={len(labels)} dev={len(dev_specs)} "
        f"attacker={len(attacker_specs)} dir={out_dir} hash={digest} overlap=pass seed={seed} "
        f"distinct_before={train_diversity['distinct_before']} "
        f"distinct_after={train_diversity['distinct_after']}"
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
    parser.add_argument(
        "--n",
        type=int,
        default=None,
        help="Pages to generate, then hold out --dev-percent. Overrides --n-train and --n-dev.",
    )
    parser.add_argument("--n-train", type=int, default=1500, help="Training pages. Default 1500.")
    parser.add_argument("--n-dev", type=int, default=300, help="Dev pages, taken as whole groups. Default 300.")
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
    if args.n is None:
        if args.n_train < 1 or args.n_dev < 0:
            raise SystemExit("--n-train must be at least 1 and --n-dev must be at least 0")
        args.count = args.n_train + args.n_dev
        args.exact_dev = args.n_dev
    else:
        if args.n < 1:
            raise SystemExit("--n must be at least 1")
        args.count = args.n
        args.exact_dev = None
    if args.seed is None:
        args.seed = seed_for_round(args.round)
    if args.out is None:
        args.out = ROOT / "data" / "trainset" / f"round{args.round}"
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    write_training(
        args.count,
        args.out,
        args.seed,
        round_n=args.round,
        attacker_dir=args.attacker,
        attacker_explicit=args.attacker is not None,
        dev_percent=args.dev_percent,
        n_dev=args.exact_dev,
    )


if __name__ == "__main__":
    main()
