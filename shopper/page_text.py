"""Compact page text for the guard.

The live page is Playwright's async page, so this awaits ``page.evaluate`` and
then uses ``gym.reader.format_extract``. That is the same extractor and the
same formatter as ``gym.reader.extract_page`` (which is synchronous).
"""

from __future__ import annotations

import json

from gym.reader import EXTRACT_JS, extract_page, format_extract

__all__ = ["EXTRACT_JS", "extract_page", "format_extract", "read_compact"]


async def read_compact(page) -> str:
    """Read whatever document is loaded in a Playwright page."""
    data = await page.evaluate(EXTRACT_JS)
    if isinstance(data, str):
        data = json.loads(data)
    return format_extract(data)
