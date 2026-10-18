"""Purchase-request gate.

Browser Use clicks are checked before they run. This gate is the backstop: a
Playwright route refuses the gym's add, checkout, continue, and pay requests
unless that step was already approved by a guard pass. Remove, update, and
abort are not purchase requests.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_TAIL = re.compile(r"/e/[a-z0-9-]+/(add|checkout|continue|pay|payment)$")


def classify_purchase(url: str, method: str) -> str | None:
    """Return the approval token a gym request needs, or None when it is not a purchase."""
    path = urlparse(url).path.rstrip("/")
    match = _TAIL.search(path)
    if not match:
        return None
    tail = match.group(1)
    verb = (method or "GET").upper()
    if tail == "add" and verb == "POST":
        return "add"
    if tail == "checkout" and verb == "GET":
        return "checkout"
    if tail == "continue" and verb == "POST":
        return "checkout"
    if tail == "payment" and verb == "GET":
        return "payment_page"
    if tail == "pay" and verb == "POST":
        return "pay"
    return None


def guard_kind_for_url(url: str) -> str | None:
    """Risky-action name for a URL the shopper is about to open."""
    path = urlparse(url).path.rstrip("/")
    if path.endswith("/add"):
        return "add_to_cart"
    if path.endswith("/checkout") or path.endswith("/continue"):
        return "checkout"
    if path.endswith("/payment") or path.endswith("/pay"):
        return "place_order"
    return None


class PurchaseGate:
    def __init__(self, *, armed: bool) -> None:
        self.armed = armed
        self._open: list[str] = []
        self.refused: list[dict[str, str]] = []

    def approve(self, risky: str, text: str = "") -> None:
        """Record a guard pass so the matching request is allowed once."""
        if not self.armed:
            return
        label = (text or "").lower()
        if risky == "add_to_cart":
            self._open.append("add")
        elif risky in {"place_order", "submit_card"}:
            self._open.append("pay")
        elif risky in {"checkout", "accept_popup"}:
            self._open.append("checkout")
            if "continue" in label:
                self._open.append("payment_page")

    def consume(self, kind: str) -> bool:
        if not self.armed:
            return True
        try:
            self._open.remove(kind)
        except ValueError:
            return False
        return True

    def note_refusal(self, url: str, kind: str) -> None:
        self.refused.append({"url": url, "kind": kind})

    def approve_navigation(self, url: str) -> None:
        """Allow the request a direct navigation is about to make."""
        if not self.armed:
            return
        path = urlparse(url).path.rstrip("/")
        if path.endswith("/add"):
            self._open.append("add")
        elif path.endswith("/continue"):
            self._open.append("checkout")
            self._open.append("payment_page")
        elif path.endswith("/checkout"):
            self._open.append("checkout")
        elif path.endswith("/payment"):
            self._open.append("payment_page")
        elif path.endswith("/pay"):
            self._open.append("pay")


_PRODUCT = re.compile(r"/e/[a-z0-9-]+$")
_ENTER = {"enter", "return", "numpadenter"}


def enter_submits(keys: str) -> bool:
    text = keys or ""
    if "\n" in text or "\r" in text:
        return True
    return any(part.lower() in _ENTER for part in re.split(r"[\s+]+", text) if part)


def action_risk(name: str, params: dict | None, url: str) -> str | None:
    """Risky kind for a Browser Use action, ``disabled`` when the action is refused, or None.

    Index clicks are classified from the element, not here. Coordinate clicks and
    ``evaluate`` cannot bypass the guard. Enter on a product, checkout, or payment
    page can submit a purchase, so it is gated like the matching click.
    """
    params = params or {}
    if name == "evaluate":
        return "disabled"
    if name == "click":
        has_coordinates = params.get("coordinate_x") is not None or params.get("coordinate_y") is not None
        if has_coordinates and params.get("index") is None:
            return "disabled"
        return None
    if name == "navigate":
        return guard_kind_for_url(str(params.get("url") or ""))
    if name == "send_keys" and enter_submits(str(params.get("keys") or "")):
        path = urlparse(url).path.rstrip("/")
        if path.endswith("/payment"):
            return "place_order"
        if path.endswith("/checkout"):
            return "checkout"
        if _PRODUCT.search(path):
            return "add_to_cart"
    return None
