"""Checkout text in the gym reader format.

The shopper reads a live page with ``gym.reader`` and posts
``format_extract`` of that extract. This module fills the same extract
from the demo store's HTML, then adds the price the product page
advertised so a fee at checkout is visible without the product page.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urlparse

from gym.reader import format_extract

_SKIP = {"script", "style", "noscript", "template"}
_VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}
_STRUCK = {"s", "del", "strike"}
_CONTROLS = {"input", "select", "textarea", "button"}


def _clean(value: str) -> str:
    return " ".join(value.split())


def _was(struck: bool, text: str) -> str:
    if text and struck and not text.lower().startswith("was"):
        return "was " + text
    return text


class _Extract(HTMLParser):
    """Stdlib stand-in for the fields ``EXTRACT_JS`` returns."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.storefront_domain = ""
        self.kind = ""
        self.prices: list[dict[str, str]] = []
        self.total = ""
        self.controls: list[dict[str, object]] = []
        self.visible: list[str] = []
        self._in_title = False
        self._in_body = False
        self._title_parts: list[str] = []
        self._skip = 0
        self._stack: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "title" and self._skip == 0:
            self._in_title = True
            self._title_parts = []
        if self._skip or tag in _SKIP:
            if tag in _SKIP:
                self._skip += 1
                self._stack.append({"tag": tag, "skip": True})
            return
        if tag in _VOID:
            if tag == "input":
                self.controls.append(_control(tag, attr, ""))
            return
        parent = self._stack[-1] if self._stack else None
        parent_struck = bool(parent and parent.get("struck"))
        classes = attr.get("class", "").split()
        self._stack.append(
            {
                "tag": tag,
                "skip": False,
                "struck": parent_struck or tag in _STRUCK or "was" in classes,
                "attrs": attr,
                "direct": [],
                "all": [],
            }
        )
        if tag == "body":
            self._in_body = True
            self.storefront_domain = attr.get("data-store-domain", "")
            self.kind = attr.get("data-page-kind", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title = _clean("".join(self._title_parts))
        if not self._stack or self._stack[-1].get("tag") != tag:
            return
        frame = self._stack.pop()
        if frame.get("skip"):
            self._skip = max(0, self._skip - 1)
            return
        attrs = frame["attrs"]
        assert isinstance(attrs, dict)
        struck = bool(frame["struck"])
        direct_parts = frame["direct"]
        all_parts = frame["all"]
        assert isinstance(direct_parts, list)
        assert isinstance(all_parts, list)
        direct = _was(struck, _clean("".join(direct_parts)))
        whole = _was(struck, _clean("".join(all_parts)))
        if self._in_body:
            if direct:
                self.visible.append(direct)
            if "data-price" in attrs:
                self.prices.append(
                    {"text": whole, "label": str(attrs.get("data-price-label", ""))}
                )
            if "data-total" in attrs and self.total == "":
                self.total = whole
            if tag in _CONTROLS:
                self.controls.append(_control(tag, attrs, whole))
        if tag == "body":
            self._in_body = False

    def handle_data(self, data: str) -> None:
        if self._in_title and self._skip == 0:
            self._title_parts.append(data)
        if self._skip or not self._stack:
            return
        top = self._stack[-1]
        if top.get("skip"):
            return
        direct = top["direct"]
        assert isinstance(direct, list)
        direct.append(data)
        for frame in self._stack:
            if frame.get("skip"):
                continue
            parts = frame["all"]
            assert isinstance(parts, list)
            parts.append(data)


def _control(tag: str, attrs: dict[str, str], label: str) -> dict[str, object]:
    type_name = (attrs.get("type") or tag).lower()
    kind = type_name if tag == "input" else tag
    checked: bool | None = None
    if type_name in ("checkbox", "radio"):
        checked = "checked" in attrs
    return {
        "kind": kind,
        "id": attrs.get("id", ""),
        "name": attrs.get("name", ""),
        "checked": checked,
        "label": label[:240],
    }


def extract_html(html: str, url: str) -> dict[str, object]:
    """Return the extract dict ``format_extract`` already knows how to render."""

    parser = _Extract()
    parser.feed(html)
    parser.close()
    parsed = urlparse(url)
    return {
        "url": url,
        "domain": parsed.hostname or "",
        "storefront_domain": parser.storefront_domain,
        "title": parser.title,
        "kind": parser.kind,
        "prices": parser.prices,
        "total": parser.total,
        "controls": parser.controls,
        "modals": [],
        "visible": parser.visible,
        "hidden": [],
        "comments": [],
    }


def checkout_reader_text(html: str, url: str, *, item: str, price: str) -> str:
    """Reader text for one checkout page, including the advertised price.

    ``item`` and ``price`` are what the product page showed. They are
    written into this page's text so the guard can see a fee that was
    not on the product page.
    """

    data = extract_html(html, url)
    visible = data.get("visible") or []
    prices = data.get("prices") or []
    assert isinstance(visible, list)
    assert isinstance(prices, list)
    data["visible"] = [f"advertised: {item} | {price}", *visible]
    data["prices"] = [{"text": price, "label": f"advertised {item}"}, *prices]
    return format_extract(data)
