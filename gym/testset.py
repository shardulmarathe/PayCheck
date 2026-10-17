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
from gym.heldout import assign_template_slices
from gym.ids import public_page_id
from gym.materialize import materialize
from gym.paths import manifest_path, replacements_path, slice_path, testset_dir
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
    assign_template_slices(specs)
    assert_rows_allowed(specs, set(test_ids))
    if len(specs) != 300:
        raise RuntimeError(f"expected 300 test pages, got {len(specs)}")
    return specs


def _legacy_id(record: dict) -> str:
    legacy = record.get("legacy_page_id") or ""
    if legacy:
        return legacy
    return record["page_id"]


def stratified_ids(records: list[dict]) -> list[str]:
    """Even stride through each attack type.

    Order is the legacy id, so renaming pages to opaque ids does not change
    which pages land in the slice. The returned ids are the public ones.
    ``records`` are labels (``attack_type``) or specs (``trick.attack_type``).
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        attack = record.get("attack_type") or record["trick"]["attack_type"]
        grouped[attack].append(record)
    chosen: list[str] = []
    for attack, count in SLICE_COUNTS.items():
        ordered = sorted(grouped.get(attack, []), key=_legacy_id)
        ids = [record["page_id"] for record in ordered]
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


def kind_mix(specs: list[dict]) -> dict[str, dict[str, int]]:
    table: dict[str, Counter[str]] = {}
    for spec in specs:
        attack = spec["trick"]["attack_type"]
        table.setdefault(attack, Counter())[spec["page"]["kind"]] += 1
    return {
        attack: dict(sorted(counts.items()))
        for attack, counts in sorted(table.items())
    }


def _write_replacements(path: Path) -> int:
    rows = []
    for row in build_specs.last_replacements:
        copied = dict(row)
        legacy = copied.get("legacy_page_id") or ""
        copied["page_id"] = public_page_id(legacy) if legacy else ""
        rows.append(copied)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": (
            "Clean descriptions dropped because the source row was a dead page, "
            "an age-restricted product, or a line that leaked a banned token. "
            "The gym page kept its legacy id. The replacement is the next usable "
            "row in the same split."
        ),
        "count": len(rows),
        "replacements": rows,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return len(rows)


def build_tree(page_dir: Path, slice_file: Path) -> tuple[list[dict], str, list[dict]]:
    specs = frozen_specs()
    if len(specs) != 300:
        raise RuntimeError(f"expected 300 test pages, got {len(specs)}")
    labels = materialize(specs, page_dir)
    _write_slice(labels, slice_file)
    digest = content_hash(page_dir, slice_file)
    return labels, digest, specs


def template_similarity(specs: list[dict]) -> dict:
    """Nearest-neighbor character similarity of each slice against round-1 train pages."""
    from gym.catalog import seed_for_round
    from gym.render import render_html
    from gym.similarity import nearest_ratios, strip_urls, summarize
    from gym.train import split_train_dev, training_specs

    seed = seed_for_round(1)
    generated = training_specs(1800, seed, round_n=1)
    train_specs, _dev_specs = split_train_dev(generated, n_dev=300)
    corpus = [strip_urls(render_html(spec)) for spec in train_specs]
    by_slice: dict[str, list[str]] = {}
    for spec in specs:
        by_slice.setdefault(spec["slice"], []).append(strip_urls(render_html(spec)))
    slices = {}
    for name in ("in_dist", "heldout_template", "heldout_attack"):
        scores = nearest_ratios(by_slice.get(name, []), corpus)
        slices[name] = summarize(scores)
        print(
            f"similarity slice={name} n={slices[name]['n']} "
            f"mean={slices[name]['mean']} max={slices[name]['max']}",
            flush=True,
        )
    return {
        "method": "rapidfuzz.fuzz.ratio on rendered HTML with URLs removed",
        "train_round": 1,
        "train_pages": len(train_specs),
        "train_seed": seed,
        "slices": slices,
    }


def write_testset() -> str:
    labels, digest, specs = build_tree(testset_dir(), slice_path())
    replaced = _write_replacements(replacements_path())
    manifest = _manifest(labels, digest)
    manifest["kinds"] = kind_mix(specs)
    manifest["slices"] = dict(sorted(Counter(spec["slice"] for spec in specs).items()))
    manifest["clean_replacements"] = replaced
    manifest["template_similarity"] = template_similarity(specs)
    heldout_mean = manifest["template_similarity"]["slices"]["heldout_template"]["mean"]
    in_dist_mean = manifest["template_similarity"]["slices"]["in_dist"]["mean"]
    if not heldout_mean or heldout_mean >= in_dist_mean or heldout_mean >= 0.85:
        raise RuntimeError(
            f"heldout_template mean {heldout_mean} is not well below the in-distribution "
            f"mean {in_dist_mean}"
        )
    manifest_path().parent.mkdir(parents=True, exist_ok=True)
    manifest_path().write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote testset pages={len(labels)} hash={digest} clean_replacements={replaced}")
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
        _labels, digest, _specs = build_tree(page_dir, slice_file)
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
