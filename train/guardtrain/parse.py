"""Parse a guard completion into the JSON contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from guardtrain.schema import ATTACK_TYPES, OUTPUT_KEYS, VERDICTS

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_SAFETY = re.compile(r"Safety:\s*(Safe|Unsafe|Controversial)", re.IGNORECASE)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think>.*", re.DOTALL | re.IGNORECASE)


def strip_think(text: str | None) -> str:
    """Drop Qwen3 thinking traces so the JSON or Safety line can be parsed."""
    cleaned = _THINK_BLOCK.sub("", text or "")
    cleaned = _THINK_OPEN.sub("", cleaned)
    return cleaned.strip()


@dataclass
class ParsedGuard:
    verdict: str
    attack_type: str
    evidence: str
    instruction: str
    parse_ok: bool
    adapter: str
    raw: str

    def as_dict(self) -> dict[str, str]:
        return {
            "verdict": self.verdict,
            "attack_type": self.attack_type,
            "evidence": self.evidence,
            "instruction": self.instruction,
        }


def _failed(raw: str, adapter: str) -> ParsedGuard:
    return ParsedGuard(
        verdict="pass",
        attack_type="none",
        evidence="",
        instruction="",
        parse_ok=False,
        adapter=adapter,
        raw=raw,
    )


def _from_mapping(obj: dict, raw: str, adapter: str) -> ParsedGuard:
    verdict = str(obj.get("verdict", "")).strip().lower()
    attack = str(obj.get("attack_type", "")).strip().lower()
    evidence = obj.get("evidence", "")
    instruction = obj.get("instruction", "")
    if not isinstance(evidence, str):
        evidence = "" if evidence is None else str(evidence)
    if not isinstance(instruction, str):
        instruction = "" if instruction is None else str(instruction)
    ok = verdict in VERDICTS and attack in ATTACK_TYPES and all(k in obj for k in OUTPUT_KEYS)
    if verdict not in VERDICTS or attack not in ATTACK_TYPES:
        return ParsedGuard(
            verdict=verdict if verdict in VERDICTS else "pass",
            attack_type=attack if attack in ATTACK_TYPES else "none",
            evidence=evidence,
            instruction=instruction,
            parse_ok=False,
            adapter=adapter,
            raw=raw,
        )
    return ParsedGuard(
        verdict=verdict,
        attack_type=attack,
        evidence=evidence,
        instruction=instruction,
        parse_ok=ok,
        adapter=adapter,
        raw=raw,
    )


def parse_json_guard(text: str) -> ParsedGuard:
    raw = strip_think(text or "")
    body = raw
    fence = _FENCE.search(body)
    if fence:
        body = fence.group(1)
    else:
        start = body.find("{")
        end = body.rfind("}")
        if start >= 0 and end > start:
            body = body[start : end + 1]
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return _failed(raw, "json")
    if not isinstance(obj, dict):
        return _failed(raw, "json")
    return _from_mapping(obj, raw, "json")


def parse_qwen3guard(text: str) -> ParsedGuard:
    raw = strip_think(text or "")
    match = _SAFETY.search(raw)
    if not match:
        return _failed(raw, "qwen3guard")
    label = match.group(1).lower()
    if label == "safe":
        return ParsedGuard(
            verdict="pass",
            attack_type="none",
            evidence="",
            instruction="",
            parse_ok=True,
            adapter="qwen3guard",
            raw=raw,
        )
    return ParsedGuard(
        verdict="block",
        attack_type="none",
        evidence="",
        instruction=(
            "Qwen3Guard flagged this page as unsafe. "
            "Stop and review the checkout before paying."
        ),
        parse_ok=True,
        adapter="qwen3guard",
        raw=raw,
    )


def parse_guard_output(text: str, *, adapter: str = "json") -> ParsedGuard:
    if adapter == "qwen3guard":
        parsed = parse_json_guard(text)
        if parsed.parse_ok:
            return parsed
        return parse_qwen3guard(text)
    if adapter == "auto":
        parsed = parse_json_guard(text)
        if parsed.parse_ok:
            return parsed
        guard = parse_qwen3guard(text)
        if guard.parse_ok:
            return guard
        return parsed
    return parse_json_guard(text)
