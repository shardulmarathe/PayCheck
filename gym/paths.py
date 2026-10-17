"""Repository paths. The package lives at the repo root."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def dataset_tsv() -> Path:
    return ROOT / "data" / "ec-darkpattern" / "dataset.tsv"


def splits_dir() -> Path:
    return ROOT / "gym" / "splits"


def train_ids_path() -> Path:
    return splits_dir() / "train_page_ids.txt"


def test_ids_path() -> Path:
    return splits_dir() / "test_page_ids.txt"


def testset_dir() -> Path:
    return ROOT / "data" / "testset"


def manifest_path() -> Path:
    return ROOT / "gym" / "testset" / "manifest.json"


def slice_path() -> Path:
    return ROOT / "gym" / "testset" / "slice100.txt"


def replacements_path() -> Path:
    return ROOT / "gym" / "testset" / "clean_replacements.json"


def schema_dir() -> Path:
    return ROOT / "gym" / "schema"
