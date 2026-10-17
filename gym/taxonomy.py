"""Attack taxonomy, split seed, and frozen-set counts.

The split seed is part of the contract. Do not change it after the id lists
in ``gym/splits/`` have been committed.
"""

from __future__ import annotations

SPLIT_SEED = 20261017
TEST_FRACTION = 0.25

ATTACK_TYPES = (
    "none",
    "hidden_fees",
    "preselected_addon",
    "price_change",
    "subscription_trap",
    "copycat_domain",
    "fake_card_verification",
    "listing_injection",
)

UPSELL = frozenset(
    {"hidden_fees", "preselected_addon", "price_change", "subscription_trap"}
)
SCAM = frozenset(
    {"copycat_domain", "fake_card_verification", "listing_injection"}
)
# Never written into training pages or the round-0 generator.
HELD_OUT = frozenset({"copycat_domain", "listing_injection"})

FAMILY = {
    "none": "clean",
    "hidden_fees": "upsell",
    "preselected_addon": "upsell",
    "price_change": "upsell",
    "subscription_trap": "upsell",
    "copycat_domain": "scam",
    "fake_card_verification": "scam",
    "listing_injection": "scam",
}

# (attack_type, variant, page kind, count). Sums to 300, half clean.
# Trick rows stay first and keep their counts so each trick slot is stable.
# Clean rows follow, and their kind counts match the trick kind counts:
# checkout 98, product 26, cart 10, payment 16.
TEST_PLAN: list[tuple[str, str, str, int]] = [
    ("hidden_fees", "drip", "checkout", 24),
    ("preselected_addon", "checkbox", "checkout", 10),
    ("preselected_addon", "modal", "cart", 10),
    ("preselected_addon", "one_click", "product", 10),
    ("price_change", "drift", "checkout", 24),
    ("subscription_trap", "autorenew", "checkout", 24),
    ("copycat_domain", "lookalike", "checkout", 16),
    ("fake_card_verification", "phishing", "payment", 16),
    ("listing_injection", "offscreen", "product", 16),
    ("none", "clean", "checkout", 98),
    ("none", "clean", "product", 26),
    ("none", "clean", "cart", 10),
    ("none", "clean", "payment", 16),
]

# Stratified 100-page slice. Counts sum to 100.
SLICE_COUNTS = {
    "hidden_fees": 8,
    "preselected_addon": 10,
    "price_change": 8,
    "subscription_trap": 8,
    "copycat_domain": 5,
    "fake_card_verification": 5,
    "listing_injection": 6,
    "none": 50,
}

# Weights sum to 100 and split about 50/50. Clean kinds mirror the trick kinds
# in the same round (checkout 34, product 3, cart 3, payment 10). Scaled to
# --n-train plus --n-dev with the largest-remainder method.
# copycat_domain and listing_injection stay out. fake_card_verification is in.
TRAIN_WEIGHTS: list[tuple[str, str, str, int]] = [
    ("none", "clean", "checkout", 34),
    ("none", "clean", "product", 3),
    ("none", "clean", "cart", 3),
    ("none", "clean", "payment", 10),
    ("hidden_fees", "drip", "checkout", 10),
    ("preselected_addon", "checkbox", "checkout", 4),
    ("preselected_addon", "modal", "cart", 3),
    ("preselected_addon", "one_click", "product", 3),
    ("price_change", "drift", "checkout", 10),
    ("subscription_trap", "autorenew", "checkout", 10),
    ("fake_card_verification", "phishing", "payment", 10),
]

VIEWPORT = (1280, 800)

STRATA = (
    "Forced Action",
    "Sneaking",
    "Obstruction",
    "Misdirection",
    "Urgency",
    "Scarcity",
    "Social Proof",
    "Not Dark Pattern",
)


def family_of(attack_type: str) -> str:
    if attack_type not in FAMILY:
        raise ValueError(f"unknown attack_type {attack_type!r}")
    return FAMILY[attack_type]


def verdict_of(attack_type: str) -> str:
    return "pass" if attack_type == "none" else "block"
