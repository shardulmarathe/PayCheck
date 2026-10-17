"""Public page ids and the neutral anchor the pages share.

The legacy id (``test-hidden_fees-000``, ``r1-none-004``) stays in the spec and
the label so a slice can keep the same pages. The rendered page, its file
name, and its URL use only the public id.
"""

from __future__ import annotations

import hashlib
import re

ANCHOR_ID = "offer-1"
SELECTOR = "#offer-1"

_SLUG = re.compile(r"[^a-z0-9]+")


def public_page_id(legacy: str) -> str:
    """Opaque id derived from the legacy id. Same legacy id, same public id."""
    digest = hashlib.sha256(legacy.encode("utf-8")).hexdigest()[:8]
    return f"p-{digest}"


def product_slug(name: str) -> str:
    slug = _SLUG.sub("-", name.casefold()).strip("-")
    return slug or "item"
