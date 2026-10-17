"""Visible text and attribute values taken from a rendered page.

Style and script text is ignored. Off-screen copy (the listing wrapper) is not
visible. The token probe also drops the ``#offer-1`` evidence element.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SPACE = re.compile(r"\s+")


class PageView(HTMLParser):
    """One pass over a page: visible text plus the attribute values the gate checks."""

    def __init__(self, *, mask_evidence: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.mask_evidence = mask_evidence
        self.skip = 0
        self.parts: list[str] = []
        self.values: set[str] = set()
        self.inputs = 0
        self.buttons = 0
        self.modals = 0
        self.passwords = 0
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs)
        self.handle_endtag(tag)

    def _start(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: "" if value is None else value for key, value in attrs}
        if tag in {"script", "style"}:
            self.skip += 1
            return
        self._collect(attr)
        classes = [token for token in (attr.get("class") or "").split() if token]
        class_set = set(classes)
        off = "offscreen" in class_set or "parked" in class_set
        hidden_attr = "hidden" in attr
        if self.skip == 0:
            if tag == "input":
                self.inputs += 1
                if (attr.get("type") or "").lower() == "password":
                    self.passwords += 1
            if tag == "button":
                self.buttons += 1
            if attr.get("role") == "dialog" or attr.get("aria-modal") == "true":
                self.modals += 1
        if off or hidden_attr:
            self.hidden += 1
        if self.skip:
            self.skip += 1
            return
        if off or hidden_attr or (self.mask_evidence and attr.get("id") == "offer-1"):
            self.skip = 1

    def _collect(self, attr: dict[str, str]) -> None:
        for key, value in attr.items():
            if value == "":
                continue
            watched = (
                key in {"id", "name", "class", "for"}
                or key.startswith("data-")
                or key.startswith("aria-")
            )
            if not watched:
                continue
            self.values.add(value)
            if key == "class":
                for token in value.split():
                    if token:
                        self.values.add(token)

    def handle_endtag(self, tag: str) -> None:
        if self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        self.parts.append(data)


def page_view(html: str, *, mask_evidence: bool = False) -> PageView:
    view = PageView(mask_evidence=mask_evidence)
    view.feed(html or "")
    view.close()
    return view


def visible_text(html: str, *, mask_evidence: bool = False) -> str:
    """Collapsed visible copy. ``mask_evidence`` drops the ``#offer-1`` subtree."""
    view = page_view(html, mask_evidence=mask_evidence)
    return _SPACE.sub(" ", " ".join(view.parts)).strip()


def visible_length(html: str) -> int:
    """Character length of visible text, including on-screen evidence."""
    return len(visible_text(html, mask_evidence=False))
