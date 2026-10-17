"""Mock shopper policy.

This is the stand-in for the LLM when ``--mock`` is set. It does not know which
errand it is on and it does not read the errand instruction. Unguarded, it
takes the prominent path: the primary control in an open dialog, then Add to
cart, Checkout, Continue, and Pay, leaving pre-checked boxes and pre-selected
radios as the page set them, and filling the payment fields the page shows.

When the guard blocks a click, the guard's instruction is appended to
``instructions``. The same policy then follows that instruction (remove the
named extra, clear a checked fee, choose one-time, or leave). That is the
only place the mock changes course.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shopper.risky import classify_click
from shopper.snapshot import Control

_WORD = re.compile(r"[a-z0-9]+")
_REMOVE_STOP = {
    "remove",
    "the",
    "a",
    "an",
    "that",
    "this",
    "popup",
    "added",
    "your",
    "cart",
    "before",
    "paying",
    "was",
    "to",
    "of",
    "and",
    "if",
    "it",
    "is",
}


@dataclass
class Action:
    kind: str
    selector: str = ""
    text: str = ""
    bbox: list[int] | None = None
    risky: str | None = None
    name: str = ""
    value: str = ""
    corrective: bool = False

    def signature(self) -> tuple[str, str, str]:
        return (self.kind, self.selector, self.text)


def _click(control: Control, risky: str | None, *, corrective: bool = False) -> Action:
    return Action(
        kind="click",
        selector=control.selector,
        text=control.label,
        bbox=list(control.bbox),
        risky=risky,
        corrective=corrective,
    )


def _words(value: str) -> set[str]:
    return {word for word in _WORD.findall(value.lower()) if word not in _REMOVE_STOP and not word.isdigit()}


def _one_time_radio(controls: list[Control]) -> Control | None:
    """The visible one-time option, whatever id the page gave the input."""
    for control in controls:
        if control.type != "radio":
            continue
        label = control.label.lower()
        if "one-time" in label or "one time" in label:
            return control
    return None


def _checked_checkbox(controls: list[Control], text: str) -> Control | None:
    """A checked box whose visible label matches the guard text.

    Ids such as ``addon`` or ``fee`` are not consulted. One checked box is
    enough when the label shares no words with the text.
    """
    boxes = [control for control in controls if control.type == "checkbox" and control.checked]
    if not boxes:
        return None
    wanted = _words(text)
    best: Control | None = None
    best_score = 0
    for box in boxes:
        score = len(wanted & _words(box.label))
        if score > best_score:
            best = box
            best_score = score
    if best is not None and best_score > 0:
        return best
    if len(boxes) == 1:
        return boxes[0]
    return None


def _leave(controls: list[Control]) -> Control | None:
    for control in controls:
        if control.label.lower().startswith("leave without"):
            return control
    return None


def _best_remove(controls: list[Control], instruction: str) -> Control | None:
    wanted = {word for word in _WORD.findall(instruction.lower()) if word not in _REMOVE_STOP}
    best: Control | None = None
    best_score = 0
    for control in controls:
        if control.tag != "button" or not control.label.lower().startswith("remove "):
            continue
        words = set(_WORD.findall(control.label.lower()))
        score = len(wanted & words)
        if score > best_score:
            best = control
            best_score = score
    return best


def follow_instruction(instruction: str, controls: list[Control]) -> Action | None:
    """Turn one guard instruction into a single corrective action, if the page can do it."""
    low = instruction.lower()
    if any(phrase in low for phrase in ("one-time", "auto-renew", "autorenew", "subscription")):
        radio = _one_time_radio(controls)
        if radio is not None and radio.checked is not True:
            return Action(
                kind="check",
                selector=radio.selector,
                text=radio.label,
                bbox=list(radio.bbox),
                corrective=True,
            )
    if any(phrase in low for phrase in ("fee", "uncheck", "add-on", "addon")):
        box = _checked_checkbox(controls, instruction)
        if box is not None:
            return Action(
                kind="uncheck",
                selector=box.selector,
                text=box.label,
                bbox=list(box.bbox),
                corrective=True,
            )
    if "remove" in low:
        button = _best_remove(controls, instruction)
        if button is not None:
            return _click(button, None, corrective=True)
    if any(
        phrase in low
        for phrase in ("do not pay", "don't pay", "do not enter", "go back", "leave without", "phishing")
    ):
        button = _leave(controls)
        if button is not None:
            return _click(button, None, corrective=True)
    return None


def _is_pay(control: Control) -> bool:
    return classify_click(control.label, control.href) in {"place_order", "submit_card"}


def naive_action(controls: list[Control]) -> Action | None:
    """Prominent path. Defaults (checked boxes, selected radios) are left alone."""
    for control in controls:
        if not (control.in_dialog and control.primary and control.tag in {"a", "button"}):
            continue
        if control.label.lower().startswith("remove ") or control.label.lower().startswith("leave without"):
            continue
        return _click(control, "accept_popup")
    for control in controls:
        if control.label.lower() == "add to cart":
            return _click(control, "add_to_cart")
    pay = [control for control in controls if _is_pay(control)]
    if pay:
        primary = [control for control in pay if control.primary]
        chosen = (primary or pay)[0]
        risky = classify_click(chosen.label, chosen.href) or "place_order"
        return Action(kind="pay", selector=chosen.selector, text=chosen.label, bbox=list(chosen.bbox), risky=risky)
    for label in ("continue to payment", "checkout"):
        matches = [control for control in controls if control.label.lower() == label]
        if not matches:
            continue
        primary = [control for control in matches if control.primary or control.tag == "a"]
        chosen = (primary or matches)[0]
        return _click(chosen, "checkout")
    return None


def choose(controls: list[Control], url: str, instructions: list[str]) -> Action | None:
    if url.rstrip("/").endswith("/done"):
        return Action(kind="done")
    if instructions:
        corrective = follow_instruction(instructions[-1], controls)
        if corrective is not None:
            return corrective
    return naive_action(controls)
