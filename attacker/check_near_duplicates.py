"""Fail if attacker spec copy near-duplicates the frozen test set.

Normalization is lowercase, punctuation stripped, whitespace collapsed.
Comparison has no minimum length, so a short test line such as "No thanks"
is a hit when it appears in spec copy. Schema fields that must reuse a fixed
token (page kind, attack type, known widget variant) are not copy.
"""

from __future__ import annotations

import ast
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS_DIR = ROOT / "attacker" / "specs" / "round1"
TEST_TEXT = ROOT / "data" / "testset" / "text"
TEST_SPECS = ROOT / "data" / "testset" / "specs"
TEST_IDS = ROOT / "gym" / "splits" / "test_page_ids.txt"
PILE = ROOT / "data" / "ec-darkpattern" / "dataset.tsv"
BUILD_PY = ROOT / "gym" / "build.py"

# Widget names the renderer keys on. They are not store copy.
KNOWN_VARIANTS = frozenset(
    {
        "drip",
        "checkbox",
        "modal",
        "one_click",
        "drift",
        "autorenew",
        "phishing",
        "lookalike",
        "offscreen",
        "clean",
        "disclosed_fee",
        "opt_in_clear",
        "real_drop",
        "legit_card",
        "mixed_honest",
        "sub_opt_in",
        "popup_decline",
        "offer_pass",
    }
)

SKIP_KEYS = frozenset(
    {
        "spec_version",
        "kind",
        "attack_type",
        "family",
        "verdict",
        "selector",
        "group_id",
        "layout",
    }
)

HELD_OUT = frozenset({"copycat_domain", "listing_injection"})

EXPECTED_ATTACKS = {
    "hidden_fees": 30,
    "preselected_addon": 30,
    "price_change": 30,
    "subscription_trap": 30,
    "fake_card_verification": 30,
    "none": 150,
}
EXPECTED_ADDON_VARIANTS = {"checkbox": 10, "modal": 10, "one_click": 10}
EXPECTED_CLEAN_VARIANTS = {
    "disclosed_fee": 25,
    "opt_in_clear": 25,
    "real_drop": 25,
    "legit_card": 25,
    "sub_opt_in": 25,
    "popup_decline": 15,
    "offer_pass": 10,
}


def normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    lowered = text.lower()
    stripped = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", stripped).strip()


def _add_phrase(bucket: set[tuple[str, ...]], slices: set[tuple[str, ...]], text: str) -> None:
    normalized = normalize(text)
    if not normalized:
        return
    tokens = tuple(normalized.split())
    if len(tokens) == 1 and tokens[0].isdigit():
        return
    bucket.add(tokens)
    if len(tokens) >= 6:
        for index in range(len(tokens) - 5):
            bucket.add(tokens[index : index + 6])
    if len(tokens) >= 2:
        limit = min(len(tokens), 12)
        for length in range(2, limit + 1):
            for index in range(len(tokens) - length + 1):
                slices.add(tokens[index : index + length])


def assert_frozen_testset() -> set[str]:
    """Fail closed when the frozen test set or its pile is missing.

    An empty corpus would otherwise let every spec pass the near-duplicate check.
    """
    problems: list[str] = []
    text_paths = sorted(TEST_TEXT.glob("*.txt")) if TEST_TEXT.is_dir() else []
    spec_paths = sorted(TEST_SPECS.glob("*.json")) if TEST_SPECS.is_dir() else []
    html_dir = TEST_TEXT.parent / "html"
    html_paths = sorted(html_dir.glob("*.html")) if html_dir.is_dir() else []
    labels_path = TEST_TEXT.parent / "labels.jsonl"
    labels: list[dict] = []
    if not labels_path.is_file():
        problems.append("missing data/testset/labels.jsonl")
    else:
        for line in labels_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                labels.append(json.loads(line))
            except json.JSONDecodeError:
                problems.append("data/testset/labels.jsonl has a row that is not JSON")
                break
    if len(text_paths) != 300:
        problems.append(f"test text pages {len(text_paths)} != 300")
    if len(spec_paths) != 300:
        problems.append(f"test specs {len(spec_paths)} != 300")
    if len(html_paths) != 300:
        problems.append(f"test html pages {len(html_paths)} != 300")
    if len(labels) != 300:
        problems.append(f"test labels {len(labels)} != 300")
    text_ids = {path.stem for path in text_paths}
    spec_ids = {path.stem for path in spec_paths}
    html_ids = {path.stem for path in html_paths}
    label_ids = {str(row.get("page_id", "")) for row in labels}
    if len(text_paths) == 300 and len(spec_paths) == 300 and len(html_paths) == 300 and len(labels) == 300:
        if not (text_ids == spec_ids == html_ids == label_ids):
            problems.append("test page ids differ across text, specs, html, and labels")
    if not TEST_IDS.is_file():
        problems.append("missing gym/splits/test_page_ids.txt")
        test_ids: set[str] = set()
    else:
        test_ids = {line.strip() for line in TEST_IDS.read_text(encoding="utf-8").splitlines() if line.strip()}
        if not test_ids:
            problems.append("gym/splits/test_page_ids.txt is empty")
    pile_rows = 0
    if not PILE.is_file():
        problems.append("missing data/ec-darkpattern/dataset.tsv")
    elif test_ids:
        with PILE.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row["page_id"].strip() in test_ids:
                    pile_rows += 1
        if pile_rows == 0:
            problems.append("test pile is empty")
    if problems:
        raise SystemExit("frozen test set check failed: " + "; ".join(problems))
    return test_ids


def load_corpus() -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    """Full phrases plus 6-word windows, and short slices for whole-field matches."""
    phrases: set[tuple[str, ...]] = set()
    slices: set[tuple[str, ...]] = set()
    test_ids = assert_frozen_testset()

    for path in sorted(TEST_TEXT.glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            _add_phrase(phrases, slices, line)

    for path in sorted(TEST_SPECS.glob("*.json")):
        _walk_strings(json.loads(path.read_text(encoding="utf-8")), phrases, slices)

    with PILE.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["page_id"].strip() in test_ids:
                _add_phrase(phrases, slices, row["text"])

    tree = ast.parse(BUILD_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            normalized = normalize(node.value)
            # Keep user-facing lines. Single code tokens ("for", "fee") are not copy.
            if normalized and len(normalized.split()) >= 2:
                _add_phrase(phrases, slices, node.value)

    return phrases, slices


def _walk_strings(value, phrases: set[tuple[str, ...]], slices: set[tuple[str, ...]]) -> None:
    if isinstance(value, str):
        _add_phrase(phrases, slices, value)
    elif isinstance(value, dict):
        for item in value.values():
            _walk_strings(item, phrases, slices)
    elif isinstance(value, list):
        for item in value:
            _walk_strings(item, phrases, slices)


def prose_strings(spec: dict) -> list[tuple[str, str]]:
    """Copy fields. Fixed schema tokens are omitted."""
    found: list[tuple[str, str]] = []

    def walk(value, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in SKIP_KEYS:
                    continue
                if key == "variant" and isinstance(item, str) and item in KNOWN_VARIANTS:
                    continue
                walk(item, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
        elif isinstance(value, str) and value.strip():
            found.append((path or "$", value))

    walk(spec, "")
    return found


def find_hits(
    spec: dict,
    phrases: set[tuple[str, ...]] | None = None,
    slices: set[tuple[str, ...]] | None = None,
) -> list[str]:
    """Return human-readable hits. Empty means the spec is clear of the test set."""
    if phrases is None or slices is None:
        phrases, slices = load_corpus()
    hits: list[str] = []
    for path, text in prose_strings(spec):
        tokens = tuple(normalize(text).split())
        if not tokens:
            continue
        # The honest-popup primary button is this exact label. Gym README
        # requires it, and the frozen pages use the same control. Any other
        # field that says "No thanks" still fails.
        if path.endswith("modal.decline") and tokens == ("no", "thanks"):
            continue
        for length in range(1, len(tokens) + 1):
            for index in range(len(tokens) - length + 1):
                window = tokens[index : index + length]
                if window in phrases:
                    hits.append(f"{path}: {' '.join(window)}")
                    break
            else:
                continue
            break
        if 2 <= len(tokens) <= 12 and tokens in slices:
            rendered = " ".join(tokens)
            needle = f"{path}: {rendered}"
            if needle not in hits:
                hits.append(f"{path} (short line inside a test page): {rendered}")
    return hits


def _load_specs(specs_dir: Path) -> list[tuple[Path, dict]]:
    paths = sorted(specs_dir.glob("*.json"))
    if not paths:
        raise SystemExit(f"no JSON specs in {specs_dir}")
    loaded = []
    for path in paths:
        loaded.append((path, json.loads(path.read_text(encoding="utf-8"))))
    return loaded


def _check_round_shape(specs: list[dict], *, round1: bool) -> list[str]:
    """Round 1 has a fixed mix. Later rounds may change counts, not the rules."""
    problems: list[str] = []
    attacks = Counter(spec["trick"]["attack_type"] for spec in specs)
    if round1 and dict(attacks) != EXPECTED_ATTACKS:
        problems.append(f"attack counts {dict(attacks)} != {EXPECTED_ATTACKS}")
    if round1:
        addon = Counter(
            spec["trick"]["variant"]
            for spec in specs
            if spec["trick"]["attack_type"] == "preselected_addon"
        )
        if dict(addon) != EXPECTED_ADDON_VARIANTS:
            problems.append(f"add-on variants {dict(addon)} != {EXPECTED_ADDON_VARIANTS}")
        clean = Counter(
            spec["trick"]["variant"] for spec in specs if spec["trick"]["attack_type"] == "none"
        )
        if dict(clean) != EXPECTED_CLEAN_VARIANTS:
            problems.append(f"clean variants {dict(clean)} != {EXPECTED_CLEAN_VARIANTS}")
    allowed = set(EXPECTED_ATTACKS)
    for spec in specs:
        trick = spec["trick"]
        attack = trick["attack_type"]
        if attack in HELD_OUT or attack not in allowed:
            problems.append(f"{spec['page_id']}: {attack} is not a training attack")
        source = spec.get("source", "")
        if not re.fullmatch(r"attacker-round[0-9]+", source) or spec.get("split") != "train":
            problems.append(f"{spec['page_id']}: source/split must be attacker-roundN/train")
        if round1 and source != "attacker-round1":
            problems.append(f"{spec['page_id']}: source/split must be attacker-round1/train")
        if "dataset_page_ids" in spec:
            problems.append(f"{spec['page_id']}: dataset_page_ids would tie the spec to the pile")
        group_id = spec.get("group_id", "")
        if not isinstance(group_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,80}", group_id):
            problems.append(f"{spec['page_id']}: group_id must name the near-duplicate family")
    return problems


def main(argv: list[str] | None = None) -> int:
    specs_dir = SPECS_DIR
    if argv:
        specs_dir = Path(argv[0])
    loaded = _load_specs(specs_dir)
    specs = [spec for _, spec in loaded]
    round1 = specs_dir.resolve() == SPECS_DIR.resolve()
    problems = _check_round_shape(specs, round1=round1)

    # Import lazily so a shape failure still reports even if gym is mid-rebase.
    from gym.validate import validate_spec

    for spec in specs:
        try:
            validate_spec(spec)
        except Exception as exc:  # noqa: BLE001 - surface validator text
            problems.append(str(exc))

    phrases, slices = load_corpus()
    hit_count = 0
    for path, spec in loaded:
        hits = find_hits(spec, phrases, slices)
        if hits:
            hit_count += 1
            problems.append(f"{path.name}: " + " | ".join(hits[:6]))

    if problems:
        print(f"near-duplicate check failed ({len(problems)} problem(s), {hit_count} spec(s) overlapped the test set)")
        for line in problems[:80]:
            print(line)
        if len(problems) > 80:
            print(f"... {len(problems) - 80} more")
        return 1

    print(
        "near-duplicate check passed "
        f"specs={len(specs)} phrases={len(phrases)} short_slices={len(slices)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
