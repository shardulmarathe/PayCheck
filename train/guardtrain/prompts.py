"""Shared guard prompt. Training and inference must use the same text.

Veri's managed ``sft_text`` path has no completion-only loss, so this system
text stays short and the shopper view is the long part of the example.
"""

from __future__ import annotations

import json
import re

from guardtrain.schema import ATTACK_TYPES, HELD_OUT_ATTACKS, OUTPUT_KEYS, LabelRow

# Held-out attack names stay in the task definition so the JSON contract is
# complete at test time. Their examples are still removed from every training file.
SYSTEM_PROMPT = """You are a checkout guard. Read one checkout page and return one JSON object. No markdown.

Keys:
- verdict: "block" or "pass".
- attack_type: hidden_fees, preselected_addon, price_change, subscription_trap, copycat_domain, fake_card_verification, listing_injection, none. Use none only when verdict is pass.
- evidence: a short quote from the page, or "" when verdict is pass.
- instruction: one short fix, or "" when verdict is pass.

Block hidden fees, preselected add-ons, price changes at checkout, subscription traps, copycat domains, fake card-verification steps, and listings injected into the page. Pass clean checkouts."""

SYSTEM_PROMPT_HIDE_HELD_OUT = SYSTEM_PROMPT.replace(
    "copycat_domain, fake_card_verification, listing_injection, none",
    "fake_card_verification, none",
).replace(
    ", copycat domains, fake card-verification steps, and listings injected into the page",
    " and fake card-verification steps",
)

GENERIC_INSTRUCTIONS = {
    "hidden_fees": "Do not pay until the extra fees are removed or the total matches the item price you were shown.",
    "preselected_addon": "Deselect every pre-checked add-on before paying.",
    "price_change": "Stop if the total changed from the price you were shown. Go back and re-check the item price.",
    "subscription_trap": "Do not start a trial or subscription. Choose a one-time purchase or leave the page.",
    "copycat_domain": "Leave this site. The domain does not match the real store.",
    "fake_card_verification": "Do not enter a card number to verify an account. Use the store's official checkout.",
    "listing_injection": "Ignore listings that were inserted into this page. Open the product from the store's own search.",
    "none": "",
}


def estimate_tokens(text: str) -> int:
    """Rough token count used only for spend pre-checks. Real calls use API usage."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max(1, max_tokens) * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[truncated]"


# Fixed user text. It must not contain the words trick, clean, or none.
USER_TASK = "Decide whether this checkout page should be blocked. Reply with one JSON object."

_URL_PATH = re.compile(r"^(url:\s*https?://[^/\s]+)/[^\s]*\s*$", re.MULTILINE)
_PAGE_ID = re.compile(
    r"\b(?:test|train|dev|attacker|r\d+)-[A-Za-z0-9_]+-\d+\b",
    re.IGNORECASE,
)
_PUBLIC_ID = re.compile(r"\bp-[0-9a-f]{8}\b", re.IGNORECASE)
_ATTACK_NAME = re.compile(
    r"\b(?:hidden_fees|preselected_addon|price_change|subscription_trap|"
    r"copycat_domain|fake_card_verification|listing_injection)\b",
    re.IGNORECASE,
)
_LABEL_WORD = re.compile(r"(?i)(?<![A-Za-z0-9])(?:trick|clean|none)(?![A-Za-z0-9])")


def shopper_page_text(text: str, page_id: str = "") -> str:
    """Drop the URL path, the page id, and label words. Keep the host.

    ``domain:`` and ``storefront_domain:`` lines stay. Copycat detection needs
    them. The path after the host contains the page id (``p-`` plus 8 hex, or a
    legacy id). Empty reader sections are the literal ``(none)``; that marker
    becomes ``(empty)`` so the label word is not in the shopper view.
    """
    cleaned = _URL_PATH.sub(r"\1", text or "")
    cleaned = cleaned.replace("(none)", "(empty)")
    if page_id:
        cleaned = cleaned.replace(page_id, "")
    cleaned = _PUBLIC_ID.sub("", cleaned)
    cleaned = _PAGE_ID.sub("", cleaned)
    cleaned = _ATTACK_NAME.sub("", cleaned)
    cleaned = _LABEL_WORD.sub("", cleaned)
    return cleaned


def build_user_message(row: LabelRow, *, max_page_tokens: int = 2000) -> str:
    """Shopper view: host, domain lines, and page text. No id and no label words."""
    text = shopper_page_text(row.page_text or "", row.page_id or "")
    text = truncate_to_tokens(text, max_page_tokens)
    return f"<page>\n{text}\n</page>\n\n{USER_TASK}"


def gold_instruction(row: LabelRow) -> str:
    if row.instruction and row.instruction.strip():
        return row.instruction.strip()
    return GENERIC_INSTRUCTIONS.get(row.attack_type, GENERIC_INSTRUCTIONS["none"])


def gold_object(row: LabelRow) -> dict[str, str]:
    """Pass rows match gym/schema: empty evidence and empty instruction."""
    if row.verdict == "pass":
        return {
            "verdict": "pass",
            "attack_type": "none",
            "evidence": "",
            "instruction": "",
        }
    return {
        "verdict": row.verdict,
        "attack_type": row.attack_type,
        "evidence": (row.evidence_text or "").strip(),
        "instruction": gold_instruction(row),
    }


def dump_output(obj: dict[str, str]) -> str:
    ordered = {key: obj.get(key, "") for key in OUTPUT_KEYS}
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def build_messages(
    row: LabelRow,
    *,
    max_page_tokens: int = 2000,
    system_in_user: bool = False,
    hide_held_out_labels: bool = False,
    include_assistant: bool = True,
    assistant_text: str | None = None,
) -> list[dict[str, str]]:
    system = SYSTEM_PROMPT_HIDE_HELD_OUT if hide_held_out_labels else SYSTEM_PROMPT
    user = build_user_message(row, max_page_tokens=max_page_tokens)
    if system_in_user:
        user = system + "\n\n" + user
        messages = [{"role": "user", "content": user}]
    else:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    if include_assistant:
        content = assistant_text if assistant_text is not None else dump_output(gold_object(row))
        messages.append({"role": "assistant", "content": content})
    return messages


def held_out_names() -> tuple[str, ...]:
    return tuple(name for name in ATTACK_TYPES if name in HELD_OUT_ATTACKS)
