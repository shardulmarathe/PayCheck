"""Class-conditional rates of structural shortcuts on a round's pages.

The four features are properties of the page, not of the label name:
a checkbox control, a popup dialog, a fee line, and a struck-through price.
Rates are computed inside each verdict and each attack type. A feature that
is common on block pages and absent on clean pages is a shortcut the guard
could learn instead of reading the trick.
"""

from __future__ import annotations

FEATURES = ("checkbox", "popup", "fee_line", "strike_through")

STRUCTURE_NOTE = (
    "Class-conditional rates of checkbox, popup, fee_line, and strike_through. "
    "Each number is the fraction of pages in that class that show the feature. "
    "A feature near 1 on block and near 0 on pass is a structure shortcut."
)


def features_of_spec(spec: dict) -> dict[str, bool]:
    """Read the four features off a trick spec. The attack name is not a feature."""
    trick = spec.get("trick") or {}
    page = spec.get("page") or {}
    variant = str(trick.get("variant") or "")
    mode = variant
    if "attack_type" in trick and "variant" in trick:
        from gym.render import trick_mode

        mode = trick_mode(spec)
    fees = page.get("fees") or []
    offers = page.get("offers") or {}
    if not isinstance(offers, dict):
        offers = {}
    listed = page.get("listed_price_cents")
    checkout = page.get("checkout_price_cents")
    checkbox = mode == "checkbox" or variant == "checkbox" or bool(offers.get("checkbox"))
    popup = mode == "modal" or variant == "modal" or bool(offers.get("modal"))
    fee_line = mode == "fee" or bool(fees)
    strike = (
        mode == "price"
        or variant == "drift"
        or bool(offers.get("was_cents"))
        or (listed is not None and checkout is not None and int(listed) != int(checkout))
    )
    return {
        "checkbox": bool(checkbox),
        "popup": bool(popup),
        "fee_line": bool(fee_line),
        "strike_through": bool(strike),
    }


def _section(text: str, start: str, end: str | None) -> list[str]:
    lines = text.splitlines()
    try:
        begin = lines.index(start)
    except ValueError:
        return []
    body = lines[begin + 1 :]
    if end is not None and end in body:
        body = body[: body.index(end)]
    return [line.strip() for line in body if line.strip()]


def features_from_page_text(text: str) -> dict[str, bool]:
    """Fallback when the spec file is not next to the labels.

    Checkbox and popup come from the reader (``controls:`` / ``modals:``).
    A fee line is a visible money line that names a fee. Strike-through is not
    in the text extract; two prices that share a label stand in for the struck
    shelf price.
    """
    raw = text or ""
    controls = _section(raw, "controls:", "modals:")
    modals = _section(raw, "modals:", "visible:")
    visible = _section(raw, "visible:", "hidden_flagged:")
    checkbox = any(line.startswith("checkbox") for line in controls)
    popup = any(line != "(none)" for line in modals)
    fee_blob = controls + visible
    fee_line = any(
        any(word in line.lower() for word in ("fee", "handling", "processing"))
        and ("$" in line or "fee" in line.lower())
        for line in fee_blob
    )
    prices = _section(raw, "prices:", "controls:" if "controls:" in raw else "visible:")
    labels: list[str] = []
    for line in prices:
        if line == "(none)":
            continue
        if " | " in line:
            labels.append(line.split(" | ", 1)[1].strip())
    strike = any(labels.count(label) >= 2 and label for label in set(labels))
    return {
        "checkbox": checkbox,
        "popup": popup,
        "fee_line": fee_line,
        "strike_through": strike,
    }


def conditional_rates(items, class_of, features_of) -> dict:
    buckets: dict[str, dict] = {}
    for item in items:
        key = str(class_of(item) or "unknown")
        feats = features_of(item)
        bucket = buckets.setdefault(key, {"n": 0, **{name: 0 for name in FEATURES}})
        bucket["n"] += 1
        for name in FEATURES:
            if feats.get(name):
                bucket[name] += 1
    out = {}
    for key in sorted(buckets):
        bucket = buckets[key]
        n = bucket["n"]
        out[key] = {"n": n}
        for name in FEATURES:
            out[key][name] = (bucket[name] / n) if n else None
    return out


def structure_block(items, *, verdict_of, attack_of, features_of) -> dict:
    return {
        "n": len(items),
        "by_verdict": conditional_rates(items, verdict_of, features_of),
        "by_attack_type": conditional_rates(items, attack_of, features_of),
    }


# Absolute gap, in rate points, between clean pages and trick pages.
PARITY_LIMIT = 0.15
_RENDERED = (
    ("checkbox", "checkbox"),
    ("popup", "popup"),
    ("fee", "fee_line"),
    ("strike", "strike_through"),
)


def rendered_feature_rates(specs: list[dict]) -> dict[str, dict[str, float | int | None]]:
    """Clean vs trick rates from rendered HTML, not from the attack name."""
    from gym.render import render_html, structural_features

    clean = [spec for spec in specs if (spec.get("trick") or {}).get("attack_type") == "none"]
    trick = [spec for spec in specs if (spec.get("trick") or {}).get("attack_type") not in {None, "none"}]
    hits = {"clean": {name: 0 for _html, name in _RENDERED}, "trick": {name: 0 for _html, name in _RENDERED}}
    for label, group in (("clean", clean), ("trick", trick)):
        for spec in group:
            found = structural_features(render_html(spec))
            for html_name, feature in _RENDERED:
                if found.get(html_name):
                    hits[label][feature] += 1
    out: dict[str, dict[str, float | int | None]] = {
        "clean_n": len(clean),
        "trick_n": len(trick),
    }
    for _html_name, feature in _RENDERED:
        clean_rate = (hits["clean"][feature] / len(clean)) if clean else None
        trick_rate = (hits["trick"][feature] / len(trick)) if trick else None
        gap = None if clean_rate is None or trick_rate is None else abs(clean_rate - trick_rate)
        out[feature] = {"clean": clean_rate, "trick": trick_rate, "gap": gap}
    return out


def parity_failures(specs: list[dict], *, where: str, limit: float = PARITY_LIMIT) -> list[str]:
    """Names of features whose clean and trick rates differ by more than ``limit``."""
    if not specs:
        return []
    rates = rendered_feature_rates(specs)
    if not rates["clean_n"] or not rates["trick_n"]:
        return []
    failures = []
    for _html_name, feature in _RENDERED:
        gap = rates[feature]["gap"]
        if gap is not None and gap > limit:
            failures.append(
                f"{where} {feature}: clean {rates[feature]['clean']:.3f} vs "
                f"trick {rates[feature]['trick']:.3f} (gap {gap:.3f} > {limit:.2f})"
            )
    return failures


def assert_structural_parity(*sides: tuple[str, list[dict]], limit: float = PARITY_LIMIT) -> dict:
    """Fail the round when a split's clean pages do not match its trick pages."""
    failures: list[str] = []
    report = {}
    for where, specs in sides:
        report[where] = rendered_feature_rates(specs)
        failures.extend(parity_failures(specs, where=where, limit=limit))
    if failures:
        raise SystemExit(
            "Refusing the round: clean and trick structural rates differ by more than "
            f"{limit:.0%} points.\n" + "\n".join(failures)
        )
    return report
