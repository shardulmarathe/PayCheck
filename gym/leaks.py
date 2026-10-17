"""Tokens that must not show up on a rendered page.

Labels may still name the attack. The HTML, the reader text, the URL, and
every id, class, and data attribute may not. Matching is on word boundaries,
so ordinary copy such as ``cleanser`` or ``latest`` is allowed.
"""

from __future__ import annotations

import re

from gym.taxonomy import ATTACK_TYPES

# Underscore is a word character, so ``hidden_fees`` is one token. A hyphen
# is not, so ``preselected-addon`` does not match ``preselected_addon``.
_WORDS = tuple(
    dict.fromkeys(
        [
            *ATTACK_TYPES,
            "trick",
            "scam",
            "attack",
            "clean",
            "none",
            "test",
            "train",
            "dev",
        ]
    )
)
_LEAK = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in sorted(_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# 404s and dead pages. "looking for" alone is a book blurb, not an error page.
_NOT_SHOPPING = re.compile(
    r"(?i)(?:"
    r"\b404\b"
    r"|doesn['’]t exist"
    r"|does not exist"
    r"|\bpage not found\b"
    r"|\bno longer available\b"
    r"|\baccess denied\b"
    r"|\bsomething went wrong\b"
    r"|\ban error occurred\b"
    r"|\berror has occurred\b"
    r"|\bpage (?:is |isn't |is not )?unavailable\b"
    r"|the page you were looking for"
    r"|\bwas taken down\b"
    r")"
)

# Nicotine, alcohol, and vapes. "Cigarette trousers" is clothing and stays.
_AGE = re.compile(
    r"(?i)\b(?:"
    r"nicotine|tobacco|vapes?|vaping|e-?cigs?|e-?cigarettes?|juul|white cloud|"
    r"alcohol|alcoholic|beers?|wines?|whisk(?:e?y)|vodkas?|tequilas?|"
    r"bourbons?|champagnes?|liquors?|liqueurs?|brand(?:y|ies)|rums?|gins?|"
    r"cannabis|marijuana|thc|cbd"
    r")\b"
)


def leak_tokens(text: str) -> list[str]:
    return [match.group(0) for match in _LEAK.finditer(text or "")]


def leaks(text: str) -> bool:
    return _LEAK.search(text or "") is not None


def leak_report(*parts: str) -> list[str]:
    """Banned tokens found in rendered HTML, reader text, or a URL."""
    found: list[str] = []
    for part in parts:
        found.extend(leak_tokens(part))
    return found


def reject_description(text: str) -> str | None:
    """Why a dataset blurb cannot be a product description, or None to keep it."""
    if _NOT_SHOPPING.search(text):
        return "not-shopping"
    if _AGE.search(text):
        return "age-restricted"
    if leaks(text):
        return "leak"
    return None


# Shopping-process copy can stay even when it is not about this SKU.
_SHOP_CHROME = re.compile(
    r"(?i)\b(?:"
    r"shipping|checkout|cookies?|privacy|accounts?|orders?|e-?mails?|"
    r"deliver(?:y|ies)|vat|payments?|carts?|wishlist|newsletters?|polic(?:y|ies)|"
    r"logins?|passwords?|estimated|inbox|discounts?|offers?|careers?|affiliates?|"
    r"sitemaps?|subscri(?:be|ption)|refunds?|warranty"
    r")\b"
)
_CAMEL = re.compile(r"[a-z][A-Z]")
# Product titles and sponsored rows from other catalogs. These read as a second listing.
_FOREIGN_LISTING = re.compile(
    r"(?i)(?:"
    r"\bt-?shirts?\b|\btees?\b|\bdresses?\b|\btrousers\b|\bsandals?\b|\bawn|"
    r"\bbouquet\b|\bcuffs?\b|\bphone stand\b|\bsleeve top\b|\bslip-on\b|"
    r"home\s*/|\bt-shirt/tee\b|/\s*tee\b|\bremote\b|\blego\b|"
    r"\bblouse\b|\bjeans\b|\bsneakers?\b|\bhoodie\b|\bshop now\b"
    r")"
)


def foreign_listing(text: str) -> bool:
    """True when a blurb is another catalog's product title or a sponsored row.

    Privacy, shipping, and account lines are not listings. A title-cased noun
    phrase, a smashed brand list, or a clothing or hardware product name is.
    """
    raw = text or ""
    if _SHOP_CHROME.search(raw):
        return False
    if _FOREIGN_LISTING.search(raw) or _CAMEL.search(raw):
        return True
    # A clipped catalog title often ends in an ellipsis. That is not a sentence.
    stripped = raw.replace("...", " ").replace("…", " ")
    words = re.findall(r"[A-Za-z0-9']+", stripped)
    if len(words) < 4 or re.search(r"[.!?]", stripped):
        return False
    caps = sum(1 for word in words if word[:1].isupper())
    return caps / len(words) >= 0.7
