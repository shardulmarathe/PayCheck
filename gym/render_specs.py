"""Render a directory of attacker trick-spec JSON files into labeled pages.

Held-out attacks are rejected unless ``--allow-held-out`` is set. Strings from
the frozen test pile are rejected unless ``--allow-test-strings`` is set, so a
training round cannot quietly absorb the test set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from gym.dataset import load_rows, load_split, norm_ws, rows_for_ids
from gym.hashing import content_hash
from gym.materialize import materialize
from gym.render import render_html
from gym.taxonomy import HELD_OUT
from gym.validate import validate_spec


def _walk_strings(value) -> list[str]:
    found: list[str] = []
    if isinstance(value, str):
        found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_strings(item))
    return found


def _banned() -> list[str]:
    rows = load_rows()
    _train_ids, test_ids = load_split()
    banned = []
    for row in rows_for_ids(rows, test_ids):
        text = norm_ws(row["text"])
        if len(text) >= 40:
            banned.append(text)
    return banned


def load_spec_dir(
    specs_dir: Path,
    *,
    source: str | None,
    allow_held_out: bool,
    allow_test_strings: bool,
) -> list[dict]:
    paths = sorted(specs_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"no JSON specs in {specs_dir}")
    banned = [] if allow_test_strings else _banned()
    specs = []
    for path in paths:
        spec = json.loads(path.read_text(encoding="utf-8"))
        if source:
            spec["source"] = source
        validate_spec(spec)
        attack = spec["trick"]["attack_type"]
        if attack in HELD_OUT and not allow_held_out:
            raise SystemExit(
                f"{path.name}: {attack} is held out of training. "
                "Pass --allow-held-out only for a test-set audit, not for training data."
            )
        if banned:
            blob = "\n".join(_walk_strings(spec))
            html = render_html(spec)
            for text in banned:
                if text in blob or text in html:
                    raise SystemExit(f"{path.name} contains a frozen test-pile string")
        specs.append(spec)
    return specs


def render_directory(
    specs_dir: Path,
    out_dir: Path,
    *,
    source: str | None = None,
    allow_held_out: bool = False,
    allow_test_strings: bool = False,
) -> str:
    specs = load_spec_dir(
        specs_dir,
        source=source,
        allow_held_out=allow_held_out,
        allow_test_strings=allow_test_strings,
    )
    labels = materialize(specs, out_dir)
    digest = content_hash(out_dir, slice_file=None)
    (out_dir / "manifest.json").write_text(
        json.dumps({"pages": len(labels), "content_hash": digest, "source": source}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"rendered specs={len(labels)} dir={out_dir} hash={digest}")
    return digest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Render attacker trick specs into labeled pages.")
    parser.add_argument("--specs-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source", default=None, help="Override source, for example attacker-round1.")
    parser.add_argument("--allow-held-out", action="store_true")
    parser.add_argument("--allow-test-strings", action="store_true")
    args = parser.parse_args(argv)
    render_directory(
        args.specs_dir,
        args.out,
        source=args.source,
        allow_held_out=args.allow_held_out,
        allow_test_strings=args.allow_test_strings,
    )


if __name__ == "__main__":
    main()
