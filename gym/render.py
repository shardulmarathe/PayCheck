"""Render a trick spec to one self-contained HTML page."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from gym.money import money
from gym.validate import selector_id, validate_spec

SKINS: dict[str, dict[str, str]] = {
    "northmart": {
        "bg": "#f3f6f1",
        "ink": "#172116",
        "muted": "#526356",
        "accent": "#1f7a3a",
        "accent_ink": "#ffffff",
        "card": "#ffffff",
        "line": "#d5e0d6",
        "soft": "#e7f2ea",
    },
    "pinepantry": {
        "bg": "#f6f3ea",
        "ink": "#241c12",
        "muted": "#655944",
        "accent": "#3f5c45",
        "accent_ink": "#ffffff",
        "card": "#fffdf8",
        "line": "#e4dccb",
        "soft": "#f3eee2",
    },
    "voltbox": {
        "bg": "#0f141c",
        "ink": "#e7eef8",
        "muted": "#9aadc4",
        "accent": "#3d8bfd",
        "accent_ink": "#04101c",
        "card": "#1a2332",
        "line": "#2c3a4e",
        "soft": "#142033",
    },
    "hearthhome": {
        "bg": "#fbf6ef",
        "ink": "#2a2118",
        "muted": "#6e5c4b",
        "accent": "#b5651d",
        "accent_ink": "#ffffff",
        "card": "#fffdf9",
        "line": "#eadfce",
        "soft": "#f8efe4",
    },
    "brightcart": {
        "bg": "#ffffff",
        "ink": "#161616",
        "muted": "#5c5c5c",
        "accent": "#d01212",
        "accent_ink": "#ffffff",
        "card": "#ffffff",
        "line": "#e6e6e6",
        "soft": "#fff1f1",
    },
}

DEFAULT_SKIN = {
    "bg": "#f7f7f5",
    "ink": "#1c1c1c",
    "muted": "#5f5f5f",
    "accent": "#1d4e89",
    "accent_ink": "#ffffff",
    "card": "#ffffff",
    "line": "#deded8",
    "soft": "#eef3f8",
}

STEP_LABELS = ("Product", "Cart", "Checkout", "Payment")


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(Path(__file__).parent / "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def due_cents(spec: dict) -> int:
    """Amount the page presents as due if the shopper accepts the trick."""
    page = spec["page"]
    trick = spec["trick"]
    subscription = page.get("subscription")
    if trick["attack_type"] == "subscription_trap" and subscription and subscription["checked"]:
        total = int(subscription["intro_price_cents"])
    elif page["cart"]:
        total = sum(int(item["qty"]) * int(item["price_cents"]) for item in page["cart"])
    else:
        total = int(page["product"]["price_cents"])
    total += sum(int(fee["amount_cents"]) for fee in page["fees"])
    addon = page.get("addon")
    if (
        addon
        and addon.get("checked")
        and trick["attack_type"] == "preselected_addon"
        and trick["variant"] == "checkbox"
        and not any(item["sku"] == addon["sku"] for item in page["cart"])
    ):
        total += int(addon["price_cents"])
    return total


def trick_mode(spec: dict) -> str:
    trick = spec["trick"]
    attack = trick["attack_type"]
    variant = trick["variant"]
    if attack == "none":
        return "none"
    if attack == "listing_injection":
        return "offscreen"
    if attack == "copycat_domain":
        return "domain"
    if attack == "fake_card_verification":
        return "phishing"
    if attack == "hidden_fees":
        return "fee"
    if attack == "price_change":
        return "price"
    if attack == "subscription_trap":
        return "subscription"
    if attack == "preselected_addon" and variant == "modal":
        return "modal"
    if attack == "preselected_addon" and variant == "one_click":
        return "one_click"
    if attack == "preselected_addon":
        return "checkbox"
    return "banner"


def page_url(spec: dict) -> str:
    domain = spec["store"]["domain"]
    kind = spec["page"]["kind"]
    return f"http://{domain}/{kind}/{spec['page_id']}"


def structural_features(html: str) -> dict[str, bool]:
    """Which trick-shaped controls a rendered page actually contains.

    Strike-through is an element (``class="was"``, ``<s>``, ``<del>``), not the
    stylesheet rule that defines the decoration. Every page's CSS mentions
    ``line-through``; that is not a sale price.
    """
    return {
        "checkbox": 'type="checkbox"' in html,
        "popup": 'role="dialog"' in html or 'aria-modal="true"' in html,
        "fee": "data-fee=" in html,
        "strike": 'class="was"' in html or "<s>" in html or "<s " in html or "<del>" in html or "<del " in html,
        "radio": 'type="radio"' in html,
    }


def _presentation(spec: dict) -> dict[str, str]:
    custom = spec["page"].get("presentation") or {}
    brand = spec["store"]["brand"]
    review = custom.get("review_line") or f"Review the total before you pay {brand}."
    return {
        "layout": custom.get("layout") or "summary-right",
        "summary": custom.get("summary") or "Order summary",
        "about": custom.get("about") or "About this item",
        "continue_label": custom.get("continue_label") or "Continue to payment",
        "add_label": custom.get("add_label") or "Add to cart",
        "pay_label": custom.get("pay_label") or "Pay now",
        "verify_label": custom.get("verify_label") or "Verify card",
        "review_line": review,
    }


def render_html(spec: dict, *, check: bool = True) -> str:
    if check:
        validate_spec(spec)
    page = spec["page"]
    trick = spec["trick"]
    mode = trick_mode(spec)
    runtime = spec.get("runtime") or {}
    live = runtime.get("mode") == "live"
    skin = dict(SKINS.get(spec["store"]["skin"], DEFAULT_SKIN))
    kind = page["kind"]
    current = _step_label(kind)
    steps = [{"label": label, "current": label == current} for label in STEP_LABELS]
    addon = page.get("addon")
    subscription = page.get("subscription")
    offers = page.get("offers") or {}
    was_cents = offers.get("was_cents")
    context = {
        "skin": skin,
        "brand": spec["store"]["brand"],
        "domain": spec["store"]["domain"],
        "category": spec["store"]["category"],
        "title": page["title"],
        "kind": kind,
        "steps": steps,
        "cart_count": sum(int(item["qty"]) for item in page["cart"]),
        "product": page["product"],
        "product_price": money(page["product"]["price_cents"]),
        "cart": [
            {
                **item,
                "price_text": money(item["price_cents"]),
                "line_text": money(int(item["qty"]) * int(item["price_cents"])),
            }
            for item in page["cart"]
        ],
        "fees": [
            {**fee, "amount_text": money(fee["amount_cents"])}
            for fee in page["fees"]
        ],
        "listed_text": money(page["listed_price_cents"]),
        "checkout_text": money(page["checkout_price_cents"]),
        "page_listed_cents": page["listed_price_cents"],
        "page_checkout_cents": page["checkout_price_cents"],
        "show_price_diff": page["listed_price_cents"] != page["checkout_price_cents"],
        "addon": None
        if addon is None
        else {**addon, "price_text": money(addon["price_cents"])},
        "subscription": None
        if subscription is None
        else {
            **subscription,
            "intro_text": money(subscription["intro_price_cents"]),
            "renewal_text": money(subscription["renewal_price_cents"]),
        },
        "total_cents": due_cents(spec),
        "total_text": money(due_cents(spec)),
        "trick_mode": mode,
        "trick_id": selector_id(trick["selector"]) if trick["selector"] else "",
        "evidence": trick["evidence_text"],
        "blocks": page["blocks"],
        "live": live,
        "presentation": _presentation(spec),
        "offers": {
            "checkbox": offers.get("checkbox"),
            "radios": offers.get("radios"),
            "modal": offers.get("modal"),
            "was_cents": was_cents,
            "was_text": money(int(was_cents)) if was_cents is not None else "",
        },
        "actions": {
            "add": runtime.get("add_action", ""),
            "remove": runtime.get("remove_action", ""),
            "checkout": runtime.get("checkout_action", ""),
            "update": runtime.get("update_action", ""),
            "continue": runtime.get("continue_action", ""),
            "pay": runtime.get("pay_action", ""),
            "abort": runtime.get("abort_action", ""),
        },
    }
    return _environment().get_template("page.html.j2").render(**context)


def _step_label(kind: str) -> str:
    return {"product": "Product", "cart": "Cart", "checkout": "Checkout", "payment": "Payment"}[kind]
