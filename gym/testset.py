"""Build and verify the frozen 300-page test set.

``python -m gym.testset --write`` creates ``data/testset`` and the manifest.
``python -m gym.testset --check`` rebuilds in a temp directory and requires the
same content hash. The check does not rewrite the committed files.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

from gym.build import assert_rows_allowed, build_specs
from gym.dataset import load_rows, load_split, rows_for_ids
from gym.hashing import content_hash
from gym.materialize import materialize
from gym.paths import manifest_path, slice_path, testset_dir
from gym.taxonomy import HELD_OUT, SLICE_COUNTS, SPLIT_SEED, TEST_FRACTION, TEST_PLAN, VIEWPORT


def frozen_specs() -> list[dict]:
    rows = load_rows()
    _train_ids, test_ids = load_split()
    specs = build_specs(
        "test",
        TEST_PLAN,
        rows_for_ids(rows, test_ids),
        seed=SPLIT_SEED,
        id_prefix="test",
    )
    assert_rows_allowed(specs, set(test_ids))
    if len(specs) != 300:
        raise RuntimeError(f"expected 300 test pages, got {len(specs)}")
    return specs


def stratified_ids(records: list[dict]) -> list[str]:
    """Even stride through each attack type, in sorted page-id order.

    ``records`` are labels (``attack_type``) or specs (``trick.attack_type``).
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for record in records:
        attack = record.get("attack_type") or record["trick"]["attack_type"]
        grouped[attack].append(record["page_id"])
    chosen: list[str] = []
    for attack, count in SLICE_COUNTS.items():
        ids = sorted(grouped.get(attack, []))
        if len(ids) < count:
            raise RuntimeError(f"{attack} has {len(ids)} pages, slice wants {count}")
        if count == len(ids):
            picked = ids
        else:
            step = len(ids) / count
            picked = [ids[int(index * step)] for index in range(count)]
        if len(set(picked)) != count:
            raise RuntimeError(f"slice for {attack} is not unique: {picked}")
        chosen.extend(picked)
    if len(chosen) != sum(SLICE_COUNTS.values()):
        raise RuntimeError("slice length mismatch")
    return sorted(chosen)


def composition(records: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for record in records:
        attack = record.get("attack_type") or record["trick"]["attack_type"]
        counts[attack] += 1
    return dict(sorted(counts.items()))


def _write_slice(records: list[dict], path: Path) -> None:
    ids = stratified_ids(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(ids) + "\n", encoding="utf-8")


def _manifest(labels: list[dict], digest: str) -> dict:
    families: Counter[str] = Counter(row["family"] for row in labels)
    return {
        "name": "checkout-guard-testset",
        "version": 1,
        "seed": SPLIT_SEED,
        "test_fraction": TEST_FRACTION,
        "viewport": list(VIEWPORT),
        "page_count": len(labels),
        "slice_count": sum(SLICE_COUNTS.values()),
        "content_hash": digest,
        "playwright": version("playwright"),
        "held_out_attack_types": sorted(HELD_OUT),
        "composition": composition(labels),
        "families": dict(sorted(families.items())),
        "slice_counts": SLICE_COUNTS,
    }


def build_tree(page_dir: Path, slice_file: Path) -> tuple[list[dict], str]:
    specs = frozen_specs()
    labels = materialize(specs, page_dir)
    _write_slice(labels, slice_file)
    digest = content_hash(page_dir, slice_file)
    return labels, digest


def write_testset() -> str:
    labels, digest = build_tree(testset_dir(), slice_path())
    manifest = _manifest(labels, digest)
    manifest_path().parent.mkdir(parents=True, exist_ok=True)
    manifest_path().write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote testset pages={len(labels)} hash={digest}")
    return digest


def _file_map(page_dir: Path) -> dict[str, bytes]:
    found = {"labels.jsonl": (page_dir / "labels.jsonl").read_bytes()}
    for folder in ("html", "text", "specs"):
        for path in sorted((page_dir / folder).iterdir()):
            if path.is_file():
                found[f"{folder}/{path.name}"] = path.read_bytes()
    return found


def check_testset() -> str:
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        page_dir = root / "pages"
        slice_file = root / "slice100.txt"
        _labels, digest = build_tree(page_dir, slice_file)
        if digest != manifest["content_hash"]:
            raise SystemExit(
                f"testset hash changed: rebuilt {digest} committed {manifest['content_hash']}"
            )
        if slice_file.read_bytes() != slice_path().read_bytes():
            raise SystemExit("slice100.txt changed")
        rebuilt = _file_map(page_dir)
        committed = _file_map(testset_dir())
        if rebuilt.keys() != committed.keys():
            raise SystemExit("testset file list changed")
        for name, data in rebuilt.items():
            if committed[name] != data:
                raise SystemExit(f"testset file changed: {name}")
    print(f"testset ok hash={digest}")
    return digest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write or verify the frozen test set.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        check_testset()
        return
    if args.write:
        write_testset()
        return
    parser.error("pass --write or --check")


if __name__ == "__main__":
    main()
