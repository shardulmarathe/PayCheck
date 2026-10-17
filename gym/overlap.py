"""Zero-overlap gate between a training round and the frozen test set.

A round fails when any generated page copies the test pile (normalized text at
any length, and a test-pile string of four or more words inside a longer
string), or shares a (store, product) pair, a price, a fee name, an add-on
name, or an evidence string with the frozen pages.
"""

from __future__ import annotations

import re
from functools import lru_cache

from gym.dataset import conflicts_with_test_pile, norm_key, test_pile_keys
from gym.money import money
from gym.render import render_html
from gym.render_specs import walk_strings

_HOST = re.compile(r"[a-z0-9][a-z0-9.-]*\.example")


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


@lru_cache(maxsize=1)
def test_surface() -> dict:
    """Identity of the frozen test set, including honest look-alike controls.

    Built from ``frozen_specs()`` so a training round is checked against the
    pages the gym would freeze, not against a stale checkout.
    """
    from gym.testset import frozen_specs

    specs = frozen_specs()
    return _surface_from_specs(specs)


def _surface_from_specs(specs: list[dict]) -> dict:
    from gym.build import ADDONS, DELTAS, FEES, LOOKALIKE, PHISH_EVIDENCE, PRODUCTS, STORES, fee_line, subscribe_line

    brands: set[str] = set()
    store_ids: set[str] = set()
    domains: set[str] = set()
    products: set[str] = set()
    skus: set[str] = set()
    fee_names: set[str] = set()
    addon_names: set[str] = set()
    pairs: set[tuple[str, str]] = set()
    cents: set[int] = set()
    evidence: set[str] = set()

    for store in STORES:
        brands.add(_fold(store["brand"]))
        store_ids.add(_fold(store["id"]))
        domains.add(store["domain"].casefold())
    domains.update(domain.casefold() for domain in LOOKALIKE.values())
    for group in PRODUCTS.values():
        for product in group:
            products.add(_fold(product["name"]))
            skus.add(product["sku"].casefold())
            price = int(product["price_cents"])
            cents.add(price)
            cents.add(max(100, price - 200))
            for delta in DELTAS:
                cents.add(price + delta)
                evidence.add(money(price + delta))
            evidence.add(subscribe_line(max(100, price - 200), price, "monthly"))
    for name, amount in FEES:
        fee_names.add(_fold(name))
        cents.add(int(amount))
        evidence.add(fee_line(name, amount))
    for name, sku, amount in ADDONS:
        addon_names.add(_fold(name))
        skus.add(sku.casefold())
        cents.add(int(amount))
        price = money(amount)
        evidence.add(f"Add {name} for {price}.")
        evidence.add(f"We added {name} to your cart for {price}.")
        evidence.add(f"Add {name} for {price} and check out in one click.")
    evidence.update(PHISH_EVIDENCE)

    for spec in specs:
        store = spec["store"]
        product = spec["page"]["product"]
        brands.add(_fold(store["brand"]))
        store_ids.add(_fold(store["id"]))
        domains.add(store["domain"].casefold())
        products.add(_fold(product["name"]))
        skus.add(product["sku"].casefold())
        pairs.add((_fold(store["id"]), _fold(product["name"])))
        pairs.add((_fold(store["brand"]), _fold(product["name"])))
        page = spec["page"]
        cents.add(int(product["price_cents"]))
        cents.add(int(page["listed_price_cents"]))
        cents.add(int(page["checkout_price_cents"]))
        for item in page["cart"]:
            cents.add(int(item["price_cents"]))
            if item.get("trick_item"):
                addon_names.add(_fold(item["name"]))
                skus.add(item["sku"].casefold())
        for fee in page["fees"]:
            fee_names.add(_fold(fee["name"]))
            cents.add(int(fee["amount_cents"]))
        addon = page.get("addon")
        if addon:
            addon_names.add(_fold(addon["name"]))
            skus.add(addon["sku"].casefold())
            cents.add(int(addon["price_cents"]))
        subscription = page.get("subscription")
        if subscription:
            cents.add(int(subscription["intro_price_cents"]))
            cents.add(int(subscription["renewal_price_cents"]))
        offers = page.get("offers") or {}
        if offers.get("was_cents") is not None:
            cents.add(int(offers["was_cents"]))
        checkbox = offers.get("checkbox") or {}
        if checkbox.get("name"):
            addon_names.add(_fold(checkbox["name"]))
        if checkbox.get("price_cents") is not None:
            cents.add(int(checkbox["price_cents"]))
        modal = offers.get("modal") or {}
        if modal.get("name"):
            addon_names.add(_fold(modal["name"]))
        if modal.get("price_cents") is not None:
            cents.add(int(modal["price_cents"]))
        quote = spec["trick"]["evidence_text"]
        if quote:
            evidence.add(quote)
        for text in walk_strings(spec):
            for host in _HOST.findall(text.casefold()):
                domains.add(host)

    evidence_keys = {norm_key(text) for text in evidence}
    evidence_keys.discard("")
    names = set(brands) | set(store_ids) | set(domains) | set(products) | set(skus)
    names |= set(fee_names) | set(addon_names)
    return {
        "brands": frozenset(brands),
        "store_ids": frozenset(store_ids),
        "domains": frozenset(domains),
        "products": frozenset(products),
        "skus": frozenset(skus),
        "fee_names": frozenset(fee_names),
        "addon_names": frozenset(addon_names),
        "pairs": frozenset(pairs),
        "cents": frozenset(cents),
        "evidence": frozenset(evidence),
        "evidence_keys": frozenset(evidence_keys),
        "names": frozenset(names),
    }


def long_evidence_keys() -> frozenset[str]:
    """Test evidence of four or more words. Training descriptions may not contain these."""
    return frozenset(key for key in test_surface()["evidence_keys"] if len(key.split()) >= 4)


def _cents_of(spec: dict) -> set[int]:
    page = spec["page"]
    found = {
        int(page["product"]["price_cents"]),
        int(page["listed_price_cents"]),
        int(page["checkout_price_cents"]),
    }
    for item in page["cart"]:
        found.add(int(item["price_cents"]))
    for fee in page["fees"]:
        found.add(int(fee["amount_cents"]))
    addon = page.get("addon")
    if addon:
        found.add(int(addon["price_cents"]))
    subscription = page.get("subscription")
    if subscription:
        found.add(int(subscription["intro_price_cents"]))
        found.add(int(subscription["renewal_price_cents"]))
    offers = page.get("offers") or {}
    if offers.get("was_cents") is not None:
        found.add(int(offers["was_cents"]))
    for key in ("checkbox", "modal"):
        block = offers.get(key) or {}
        if block.get("price_cents") is not None:
            found.add(int(block["price_cents"]))
    return found


def _names_of(spec: dict) -> tuple[set[str], set[str]]:
    fees = {_fold(fee["name"]) for fee in spec["page"]["fees"]}
    addons: set[str] = set()
    addon = spec["page"].get("addon")
    if addon:
        addons.add(_fold(addon["name"]))
    offers = spec["page"].get("offers") or {}
    for key in ("checkbox", "modal"):
        block = offers.get(key) or {}
        if block.get("name"):
            addons.add(_fold(block["name"]))
    for item in spec["page"]["cart"]:
        if item.get("trick_item"):
            addons.add(_fold(item["name"]))
    return fees, addons


def overlap_problems(specs: list[dict]) -> list[str]:
    """Human-readable collisions. Empty means the round is clear of the test set."""
    from gym.build import mentions_real_brand

    surface = test_surface()
    banned = test_pile_keys()
    long_keys = [key for key in surface["evidence_keys"] if len(key.split()) >= 4]
    problems: list[str] = []
    for spec in specs:
        page_id = spec["page_id"]
        store = spec["store"]
        product = spec["page"]["product"]
        pair_id = (_fold(store["id"]), _fold(product["name"]))
        pair_brand = (_fold(store["brand"]), _fold(product["name"]))
        if pair_id in surface["pairs"] or pair_brand in surface["pairs"]:
            problems.append(f"{page_id}: shares a (store, product) pair with the test set")
        if _fold(store["brand"]) in surface["brands"] or store["id"].casefold() in surface["store_ids"]:
            problems.append(f"{page_id}: uses a test store ({store['brand']})")
        if store["domain"].casefold() in surface["domains"]:
            problems.append(f"{page_id}: uses a test domain ({store['domain']})")
        if _fold(product["name"]) in surface["products"]:
            problems.append(f"{page_id}: uses a test product ({product['name']})")
        fees, addons = _names_of(spec)
        copied_fees = fees & surface["fee_names"]
        if copied_fees:
            problems.append(f"{page_id}: fee name overlaps the test set ({sorted(copied_fees)[0]})")
        copied_addons = addons & surface["addon_names"]
        if copied_addons:
            problems.append(f"{page_id}: add-on name overlaps the test set ({sorted(copied_addons)[0]})")
        copied_cents = _cents_of(spec) & surface["cents"]
        if copied_cents:
            problems.append(f"{page_id}: price point overlaps the test set ({money(min(copied_cents))})")
        quote = spec["trick"]["evidence_text"]
        if quote and (quote in surface["evidence"] or norm_key(quote) in surface["evidence_keys"]):
            problems.append(f"{page_id}: evidence overlaps the test set")
        blob_parts = walk_strings(spec)
        for text in blob_parts:
            if conflicts_with_test_pile(text, banned):
                problems.append(f"{page_id}: normalized test-pile string in the spec")
                break
            if mentions_real_brand(text):
                problems.append(f"{page_id}: real brand name in the spec")
                break
        else:
            html = render_html(spec)
            if conflicts_with_test_pile(html, banned):
                problems.append(f"{page_id}: normalized test-pile string in the rendered page")
            else:
                folded = norm_key(html)
                for key in long_keys:
                    if key in folded:
                        problems.append(f"{page_id}: rendered page contains test evidence")
                        break
    return problems


def assert_no_test_overlap(specs: list[dict], label: str = "round") -> None:
    problems = overlap_problems(specs)
    if problems:
        preview = "\n".join(problems[:20])
        extra = "" if len(problems) <= 20 else f"\n... {len(problems) - 20} more"
        raise SystemExit(f"{label} overlaps the frozen test set ({len(problems)}):\n{preview}{extra}")
