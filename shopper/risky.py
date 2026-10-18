"""Which clicks can change the cart or pay.

Classification uses the control the shopper is about to use (its text, href,
and whether it is the primary control inside a dialog). It does not look at
the errand id.
"""

from __future__ import annotations

PAY_TEXTS = {
    "pay now",
    "place order",
    "complete purchase",
    "submit payment",
    "submit order",
    "verify card",
    "submit card",
}


def classify_click(text: str, href: str = "", *, in_dialog: bool = False, primary: bool = False) -> str | None:
    """Return a risky-action name, or None when the click is not gated."""
    label = " ".join((text or "").split()).lower()
    link = (href or "").split("?", 1)[0].rstrip("/").lower()
    if label.startswith("remove ") or label.startswith("leave without"):
        return None
    if in_dialog and primary:
        return "accept_popup"
    if label == "add to cart" or link.endswith("/add"):
        return "add_to_cart"
    if label in {"checkout", "continue to payment"} or link.endswith("/checkout"):
        return "checkout"
    if label in PAY_TEXTS or link.endswith("/pay"):
        if "verify" in label:
            return "submit_card"
        return "place_order"
    return None
