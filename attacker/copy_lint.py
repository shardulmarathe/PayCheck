"""Lint attacker page copy for narrator tells and class-conditional vocabulary.

Diversity is measured on the same sentences the round-1 review counted:
product description, block text, and evidence, split on . ! ?.
Masking replaces catalog names and money amounts, then strips punctuation.
"""

from __future__ import annotations

import re
from collections import Counter

from attacker.check_near_duplicates import normalize

# Narrator lines that state or hint the verdict. Ordinary store facts are allowed.
BANNED_PHRASES = (
    "was not part of the tag",
    "not part of the tag",
    "the tag never listed",
    "never listed",
    "was silent about",
    "sits outside the tag",
    "outside the tag",
    "is new once you reach",
    "you do not meet",
    "that drop is real",
    "the drop is real",
    "is the real drop",
    "real drop",
    "will not rise later",
    "stays off the amount due",
    "off the amount due",
    "outside the amount due",
    "the box is empty",
    "box is empty",
    "is not ticked",
    "not ticked",
    "starts ticked",
    "stays ticked",
    "already marked",
    "already selected",
    "pre-selected",
    "preselected",
    "you did not choose",
    "did not choose",
    "the window placed",
    "window placed",
    "nothing further is introduced",
    "matches the tag",
    "matches the earlier quote",
    "earlier quote",
    "was printed under",
    "printed under the tag",
    "no packing line",
    "no repeat parcel",
    "carrier cost is inside",
    "the shop you opened",
    "leave without paying",
    "refuse the higher",
    "bank site secret",
    "sign-in secret",
    "this is a trick",
    "dark pattern",
    "hidden fee",
    "clearly disclosed",
    "nothing was added",
    "without your consent",
    "automatically added",
    "you can trust",
    "safe to pay",
    "this page is clean",
    "above the tag",
    "replaced the lower tag",
    "taken the place of the tag",
    "not the one marked",
    "turn the repeat off",
    "single parcel",
    "quiet button",
    "filled button",
    "if you can clear",
)

_NUM_WORD = (
    "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|"
    "fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    "sixty|seventy|eighty|ninety"
)
_MONEY = re.compile(
    rf"\$(?:\d{{1,3}}(?:,\d{{3}})*|\d+)(?:\.\d{{2}})?|"
    rf"(?:{_NUM_WORD})(?:[\s-](?:{_NUM_WORD}))*\s+dollars?"
    rf"(?:\s+and\s+(?:{_NUM_WORD})(?:[\s-](?:{_NUM_WORD}))*\s+cents?)?|"
    rf"(?:{_NUM_WORD})(?:[\s-](?:{_NUM_WORD}))*\s+cents?",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    return [part.strip() for part in _SENTENCE.split(stripped) if part.strip()]


def offer_copy(page: dict) -> list[str]:
    """Visible honest-control copy. The fixed decline button is chrome."""
    offers = page.get("offers") or {}
    fields: list[str] = []
    checkbox = offers.get("checkbox") or {}
    if checkbox.get("label"):
        fields.append(checkbox["label"])
    modal = offers.get("modal") or {}
    if modal.get("text"):
        fields.append(modal["text"])
    if modal.get("accept"):
        fields.append(modal["accept"])
    for option in (offers.get("radios") or {}).get("options") or []:
        if option.get("label"):
            fields.append(option["label"])
    return fields


def copy_sentences(spec: dict) -> list[str]:
    """Page sentences a shopper can read, excluding the shopper instruction."""
    page = spec["page"]
    fields = [page["product"]["description"]]
    fields.extend(block["text"] for block in page["blocks"])
    fields.extend(offer_copy(page))
    evidence = spec["trick"]["evidence_text"]
    if evidence.strip():
        fields.append(evidence)
    sentences: list[str] = []
    for text in fields:
        sentences.extend(split_sentences(text))
    return sentences


def lint_sentences(spec: dict) -> list[str]:
    """Every authored sentence, including the instruction and control labels."""
    page = spec["page"]
    fields = [
        page["title"],
        page["product"]["description"],
        spec["trick"]["evidence_text"],
        spec["trick"]["instruction"],
    ]
    fields.extend(block["text"] for block in page["blocks"])
    fields.extend(offer_copy(page))
    fields.extend(fee["name"] for fee in page["fees"])
    addon = page.get("addon")
    if addon:
        fields.append(addon["name"])
    subscription = page.get("subscription")
    if subscription:
        fields.append(subscription["option_label"])
        fields.append(subscription["cadence"])
    sentences: list[str] = []
    for text in fields:
        sentences.extend(split_sentences(text) or ([text.strip()] if text.strip() else []))
    return sentences


def catalog_names(specs: list[dict]) -> list[str]:
    names: set[str] = set()
    for spec in specs:
        store = spec["store"]
        names.update({store["brand"], store["domain"], store["id"]})
        product = spec["page"]["product"]
        names.update({product["name"], product["sku"]})
        for item in spec["page"]["cart"]:
            names.update({item["name"], item["sku"]})
        for fee in spec["page"]["fees"]:
            names.add(fee["name"])
        addon = spec["page"].get("addon")
        if addon:
            names.update({addon["name"], addon["sku"]})
        subscription = spec["page"].get("subscription")
        if subscription:
            names.add(subscription["option_label"])
    return sorted((name for name in names if name and len(name) > 1), key=len, reverse=True)


def mask_text(text: str, names: list[str]) -> str:
    masked = text
    for name in names:
        masked = re.sub(re.escape(name), " NAME ", masked, flags=re.IGNORECASE)
    masked = _MONEY.sub(" PRICE ", masked)
    masked = normalize(masked)
    masked = re.sub(r"(?:\bname\b\s*)+", "name ", masked)
    masked = re.sub(r"(?:\bprice\b\s*)+", "price ", masked)
    return re.sub(r"\s+", " ", masked).strip()


def diversity_stats(specs: list[dict]) -> dict[str, float]:
    names = catalog_names(specs)
    raw: list[str] = []
    masked: list[str] = []
    for spec in specs:
        for sentence in copy_sentences(spec):
            raw.append(sentence)
            masked.append(mask_text(sentence, names))
    total = len(raw) or 1
    distinct_raw = len(set(raw))
    distinct_masked = len(set(masked))
    return {
        "sentences": float(len(raw)),
        "distinct_raw": float(distinct_raw),
        "distinct_raw_ratio": distinct_raw / total,
        "distinct_masked": float(distinct_masked),
        "distinct_masked_ratio": distinct_masked / total,
    }


def banned_hits(spec: dict) -> list[str]:
    hits: list[str] = []
    for sentence in lint_sentences(spec):
        tokens = tuple(normalize(sentence).split())
        for phrase in BANNED_PHRASES:
            needle = tuple(normalize(phrase).split())
            width = len(needle)
            if width == 0 or len(tokens) < width:
                continue
            for index in range(len(tokens) - width + 1):
                if tokens[index : index + width] == needle:
                    hits.append(f"{phrase} :: {sentence}")
                    break
    return hits


def page_tokens(spec: dict, names: list[str]) -> set[str]:
    """Tokens left after names and prices are masked out of shopper-visible copy."""
    found: set[str] = set()
    for sentence in copy_sentences(spec):
        for token in mask_text(sentence, names).split():
            if token not in {"name", "price"}:
                found.add(token)
    return found


def skewed_tokens(specs: list[dict], *, limit: float = 0.10) -> list[str]:
    """Tokens on more than `limit` of one class and none of the other.

    Class is clean (`attack_type` none) versus every attack page.
    """
    names = catalog_names(specs)
    clean = [spec for spec in specs if spec["trick"]["attack_type"] == "none"]
    attack = [spec for spec in specs if spec["trick"]["attack_type"] != "none"]
    if not clean or not attack:
        return ["need both clean pages and attack pages"]
    clean_counts: Counter[str] = Counter()
    attack_counts: Counter[str] = Counter()
    for spec in clean:
        clean_counts.update(page_tokens(spec, names))
    for spec in attack:
        attack_counts.update(page_tokens(spec, names))
    bad: list[str] = []
    for token in set(clean_counts) | set(attack_counts):
        clean_share = clean_counts[token] / len(clean)
        attack_share = attack_counts[token] / len(attack)
        if clean_share > limit and attack_counts[token] == 0:
            bad.append(
                f"{token}: clean {clean_counts[token]}/{len(clean)} ({clean_share:.1%}), attack 0"
            )
        elif attack_share > limit and clean_counts[token] == 0:
            bad.append(
                f"{token}: attack {attack_counts[token]}/{len(attack)} ({attack_share:.1%}), clean 0"
            )
    return sorted(bad)


def lint_specs(specs: list[dict]) -> list[str]:
    problems: list[str] = []
    for spec in specs:
        for hit in banned_hits(spec):
            problems.append(f"{spec['page_id']}: {hit}")
    problems.extend(skewed_tokens(specs))
    stats = diversity_stats(specs)
    if stats["distinct_raw_ratio"] < 0.80:
        problems.append(
            f"distinct sentences {stats['distinct_raw_ratio']:.1%} < 80% "
            f"({int(stats['distinct_raw'])}/{int(stats['sentences'])})"
        )
    if stats["distinct_masked_ratio"] < 0.50:
        problems.append(
            f"distinct masked sentences {stats['distinct_masked_ratio']:.1%} < 50% "
            f"({int(stats['distinct_masked'])}/{int(stats['sentences'])})"
        )
    return problems
