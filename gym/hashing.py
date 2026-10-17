"""Content hash for a frozen page directory.

The hash covers labels, the slice id list, rendered HTML, extracted text, and
specs. It does not cover ``manifest.json``, because that file stores the hash.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def _add(hasher: hashlib._Hash, label: str, data: bytes) -> None:
    hasher.update(label.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(hashlib.sha256(data).digest())


def content_hash(page_dir: Path, slice_file: Path | None = None) -> str:
    hasher = hashlib.sha256()
    labels = page_dir / "labels.jsonl"
    _add(hasher, "labels", labels.read_bytes())
    if slice_file is not None:
        _add(hasher, "slice", slice_file.read_bytes())
    for folder in ("html", "text", "specs"):
        directory = page_dir / folder
        for path in sorted(directory.iterdir()):
            if path.is_file():
                _add(hasher, f"{folder}/{path.name}", path.read_bytes())
    return hasher.hexdigest()
