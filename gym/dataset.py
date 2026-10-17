"""Load the Yada ec-darkpattern TSV and the committed page-id split.

Split membership is defined by :func:`compute_split` and frozen in
``gym/splits/*.txt``. Training code must load strings through
:func:`rows_for_ids` with the train id list, never by re-shuffling.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from gym.paths import dataset_tsv, test_ids_path, train_ids_path
from gym.taxonomy import HELD_OUT, SPLIT_SEED, STRATA, TEST_FRACTION

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)


def norm_ws(text: str) -> str:
    """Collapse whitespace so a quoted string is one exact visible line."""
    return _WS.sub(" ", text).strip()


def norm_key(text: str) -> str:
    """Lowercase, turn punctuation into spaces, and collapse whitespace.

    Used to compare dataset strings that differ only by case or punctuation.
    """
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


@lru_cache(maxsize=1)
def test_pile_keys() -> frozenset[str]:
    """Normalized text of every test-pile row, including strings shorter than 40 characters."""
    rows = load_rows()
    _train_ids, test_ids = load_split()
    keys = {norm_key(row["text"]) for row in rows_for_ids(rows, test_ids)}
    keys.discard("")
    return frozenset(keys)


def conflicts_with_test_pile(text: str, banned: frozenset[str] | set[str] | None = None) -> bool:
    """True when ``text`` is a test-pile string, or contains one of four or more words.

    One- and two-word pile strings are banned only as a whole line. Matching
    those as substrings would reject ordinary words such as "or".
    """
    key = norm_key(text)
    if not key:
        return False
    pool = test_pile_keys() if banned is None else banned
    if key in pool:
        return True
    for item in pool:
        if len(item.split()) >= 4 and item in key:
            return True
    return False


def load_rows(path: Path | None = None) -> list[dict[str, str]]:
    source = path or dataset_tsv()
    rows: list[dict[str, str]] = []
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        expected = ["page_id", "text", "label", "Pattern Category"]
        if reader.fieldnames != expected:
            raise ValueError(f"unexpected columns {reader.fieldnames!r}")
        for raw in reader:
            page_id = raw["page_id"].strip()
            label = raw["label"].strip()
            if not page_id.isdigit() or label not in {"0", "1"}:
                raise ValueError(f"bad row page_id={page_id!r} label={label!r}")
            rows.append(
                {
                    "page_id": page_id,
                    "text": raw["text"],
                    "label": label,
                    "category": raw["Pattern Category"].strip(),
                }
            )
    if len(rows) != 2356:
        raise ValueError(f"expected 2356 rows, found {len(rows)}")
    return rows


def _stratum(rows_for_page: list[dict[str, str]]) -> str:
    cats = {row["category"] for row in rows_for_page if row["category"] != "Not Dark Pattern"}
    if not cats:
        return "Not Dark Pattern"
    for name in STRATA:
        if name in cats:
            return name
    return sorted(cats)[0]


def _seed_for(stratum: str) -> int:
    digest = hashlib.sha256(f"{SPLIT_SEED}:{stratum}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _shuffle(items: list[str], rng: random.Random) -> list[str]:
    """Fisher-Yates driven by Random.randrange. Explicit so the split cannot drift with Random.shuffle."""
    out = list(items)
    for index in range(len(out) - 1, 0, -1):
        swap = rng.randrange(index + 1)
        out[index], out[swap] = out[swap], out[index]
    return out


def test_count(size: int) -> int:
    """Round half up, and keep both piles non-empty when a stratum has 2+ pages."""
    if size <= 0:
        return 0
    count = int(size * TEST_FRACTION + 0.5)
    if size >= 2:
        count = min(max(count, 1), size - 1)
    return count


def compute_split(rows: list[dict[str, str]] | None = None) -> tuple[list[str], list[str]]:
    """Return ``(train_ids, test_ids)``, each sorted numerically.

    Pages are stratified by pattern category so rare categories land in both
    piles. Every string that shares a ``page_id`` stays in the same pile.
    """
    rows = load_rows() if rows is None else rows
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["page_id"]].append(row)
    strata: dict[str, list[str]] = defaultdict(list)
    for page_id, page_rows in grouped.items():
        strata[_stratum(page_rows)].append(page_id)

    train: list[str] = []
    test: list[str] = []
    for stratum in STRATA:
        ids = sorted(strata.get(stratum, []), key=lambda value: int(value))
        if not ids:
            continue
        rng = random.Random(_seed_for(stratum))
        shuffled = _shuffle(ids, rng)
        holdout = test_count(len(shuffled))
        test.extend(shuffled[:holdout])
        train.extend(shuffled[holdout:])
    # Any unexpected stratum still has to be assigned, deterministically.
    for stratum in sorted(set(strata) - set(STRATA)):
        ids = sorted(strata[stratum], key=lambda value: int(value))
        rng = random.Random(_seed_for(stratum))
        shuffled = _shuffle(ids, rng)
        holdout = test_count(len(shuffled))
        test.extend(shuffled[:holdout])
        train.extend(shuffled[holdout:])
    train_sorted = sorted(set(train), key=lambda value: int(value))
    test_sorted = sorted(set(test), key=lambda value: int(value))
    if set(train_sorted) & set(test_sorted):
        raise RuntimeError("split overlap")
    if set(train_sorted) | set(test_sorted) != set(grouped):
        raise RuntimeError("split does not cover every page_id")
    return train_sorted, test_sorted


def read_id_list(path: Path) -> list[str]:
    ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if ids != sorted(ids, key=lambda value: int(value)):
        raise ValueError(f"{path} is not in numeric order")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path} has duplicate ids")
    return ids


def load_split() -> tuple[list[str], list[str]]:
    return read_id_list(train_ids_path()), read_id_list(test_ids_path())


def write_split_files(force: bool = False) -> tuple[list[str], list[str]]:
    train, test = compute_split()
    for path, ids in ((train_ids_path(), train), (test_ids_path(), test)):
        payload = "\n".join(ids) + "\n"
        if path.exists() and not force:
            current = path.read_text(encoding="utf-8")
            if current != payload:
                raise SystemExit(
                    f"{path} already exists and does not match this seed. "
                    "The split is frozen; refusing to rewrite it."
                )
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    return train, test


def rows_for_ids(rows: list[dict[str, str]], ids: list[str] | set[str]) -> list[dict[str, str]]:
    allowed = set(ids)
    return [row for row in rows if row["page_id"] in allowed]


def classify_evidence(text: str, category: str) -> str | None:
    """Map a dark-pattern string onto one guard attack, or None.

    Urgency, scarcity, and social proof are outside the guard taxonomy, so
    they stay in the split pools and are not rendered as a second trick.
    ``copycat_domain`` and ``listing_injection`` are not in this dataset.
    """
    folded = text.lower()
    fee_keys = (
        "service charge",
        "care & handling",
        "care and handling",
        "shipping insurance",
        "order subtotal",
        "standard delivery",
        "item total",
        "processing fee",
    )
    if any(key in folded for key in fee_keys):
        return "hidden_fees"
    if category == "Sneaking" and "$" in text and "total" in folded:
        return "hidden_fees"
    subscription_keys = (
        "subscri",
        "auto renew",
        "autorenew",
        "automatically renew",
        "recurring",
        "per month",
        "membership",
        "cancel your",
        "vip trial",
        "renews",
        "renewal",
        "billed monthly",
    )
    if category == "Obstruction" or any(key in folded for key in subscription_keys):
        return "subscription_trap"
    addon_keys = (
        "protect",
        "protection",
        "no thanks",
        "pay full",
        "rather pay",
        "don't want",
        "don’t want",
        "tempt you",
        "uncheck",
        "add and save",
        "ship it for free",
        "agree to",
        "opt in",
        "opt-in",
    )
    if category == "Forced Action" or any(key in folded for key in addon_keys):
        return "preselected_addon"
    return None


def held_out_types() -> frozenset[str]:
    return HELD_OUT


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Check or write the frozen page-id split.")
    parser.add_argument("--check", action="store_true", help="Exit 1 if the files differ from the seed.")
    parser.add_argument("--write", action="store_true", help="Write the id lists if they are missing.")
    args = parser.parse_args(argv)
    if args.check:
        expected_train, expected_test = compute_split()
        actual_train, actual_test = load_split()
        if actual_train != expected_train or actual_test != expected_test:
            raise SystemExit("committed split does not match the seed algorithm")
        print(f"split ok train={len(actual_train)} test={len(actual_test)}")
        return
    if args.write:
        train, test = write_split_files()
        print(f"wrote split train={len(train)} test={len(test)}")
        return
    parser.error("pass --check or --write")


if __name__ == "__main__":
    main()
