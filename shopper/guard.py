"""Checkout guard client.

``mock`` compares the page text with the gym's own labels: the live errand
catalog (``/errands.json`` harness block) and, for frozen pages, ``labels.jsonl``.
A label blocks only when its evidence is actually on the page and the trick is
still armed (a fee checkbox still checked, a one-time radio not yet chosen).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from gym.paths import schema_dir, testset_dir

PASS = {"verdict": "pass", "attack_type": "none", "evidence": "", "instruction": ""}

_SPACE = re.compile(r"\s+")
_ERRAND_URL = re.compile(r"/e/([a-z0-9-]+)\b")


def normalize(value: str) -> str:
    return _SPACE.sub(" ", value or "").strip()


def _armed(attack_type: str, text: str) -> bool:
    """Whether the matched label is still the dangerous state of the page."""
    if attack_type == "hidden_fees" and "id=fee" in text:
        return "checkbox checked | id=fee" in text
    if attack_type == "subscription_trap" and "id=purchase-once" in text:
        return "radio checked | id=purchase-once" not in text
    if attack_type == "preselected_addon" and "id=addon" in text:
        return "checkbox checked | id=addon" in text
    return True


@dataclass(frozen=True)
class LabelRule:
    attack_type: str
    variant: str
    evidence: str
    instruction: str
    source: str
    errand_id: str = ""
    page_id: str = ""


def rules_from_catalog(catalog: list[dict]) -> list[LabelRule]:
    rules = []
    for errand in catalog:
        harness = errand.get("harness") or {}
        evidence = harness.get("evidence") or ""
        if not evidence:
            continue
        rules.append(
            LabelRule(
                attack_type=harness.get("attack_type") or "none",
                variant=harness.get("variant") or "",
                evidence=evidence,
                instruction=harness.get("guard_instruction") or "",
                source="errand",
                errand_id=errand.get("id") or "",
            )
        )
    return rules


def rules_from_labels(path: Path | None = None) -> list[LabelRule]:
    label_path = path or (testset_dir() / "labels.jsonl")
    if not label_path.is_file():
        return []
    rules = []
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("verdict") != "block" or not row.get("evidence_text"):
            continue
        rules.append(
            LabelRule(
                attack_type=row["attack_type"],
                variant="",
                evidence=row["evidence_text"],
                instruction=row.get("instruction") or "",
                source="label",
                page_id=row.get("page_id") or "",
            )
        )
    return rules


class MockGuard:
    def __init__(self, catalog: list[dict], labels: list[LabelRule] | None = None) -> None:
        self.errand_rules = rules_from_catalog(catalog)
        self.label_rules = list(labels) if labels is not None else rules_from_labels()

    def check(self, text: str) -> dict[str, str]:
        folded = normalize(text)
        errand_id = ""
        match = _ERRAND_URL.search(folded)
        if match:
            errand_id = match.group(1)
        if errand_id:
            pool = [rule for rule in self.errand_rules if rule.errand_id == errand_id]
        else:
            pool = [rule for rule in self.label_rules if len(normalize(rule.evidence)) >= 20]
            pool.extend(self.errand_rules)
        hits = []
        for rule in pool:
            evidence = normalize(rule.evidence)
            # Short strings false-positive across the frozen set, so they only
            # count for the errand whose URL is on the page. "$12.49" is the
            # whole price-change evidence and has to match there.
            if len(evidence) < 12 and not (errand_id and rule.source == "errand" and rule.errand_id == errand_id):
                continue
            if not evidence or evidence not in folded:
                continue
            if not _armed(rule.attack_type, folded):
                continue
            hits.append(rule)
        if not hits:
            return dict(PASS)
        hits.sort(key=lambda rule: len(rule.evidence), reverse=True)
        rule = hits[0]
        return {
            "verdict": "block",
            "attack_type": rule.attack_type,
            "evidence": rule.evidence,
            "instruction": rule.instruction,
        }


def validate_guard_output(payload: dict) -> dict[str, str]:
    required = ("verdict", "attack_type", "evidence", "instruction")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"guard response missing {', '.join(missing)}")
    if payload["verdict"] not in {"block", "pass"}:
        raise ValueError("guard verdict must be block or pass")
    return {key: payload[key] if isinstance(payload[key], str) else str(payload[key]) for key in required}


class GuardClient:
    def __init__(self, *, backend: str, guard_url: str | None, catalog: list[dict]) -> None:
        if backend not in {"mock", "http"}:
            raise ValueError(backend)
        self.backend = backend
        self.guard_url = (guard_url or "").rstrip("/")
        self.mock = MockGuard(catalog)
        self.endpoint = "mock" if backend == "mock" else f"{self.guard_url}/check"

    async def check(self, text: str, *, url: str, action: str, target: str) -> tuple[dict[str, str], float]:
        started = time.perf_counter()
        if self.backend == "mock":
            payload = self.mock.check(text)
        else:
            if not self.guard_url:
                raise RuntimeError("guard URL is required when --guard-backend http")
            body = {"text": text, "url": url, "action": action, "target": target}
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(self.endpoint, json=body)
                response.raise_for_status()
                payload = response.json()
        latency_ms = (time.perf_counter() - started) * 1000
        return validate_guard_output(payload), round(latency_ms, 3)


def load_catalog(base_url: str) -> list[dict]:
    import urllib.request

    with urllib.request.urlopen(base_url.rstrip("/") + "/errands.json", timeout=10) as response:
        payload = json.loads(response.read().decode())
    errands = payload.get("errands")
    if not isinstance(errands, list) or not errands:
        raise RuntimeError(f"no errands at {base_url}/errands.json")
    return errands


def guard_schema_path() -> Path:
    return schema_dir() / "guard_output.json"


def check_guard_output_schema(payload: dict[str, Any]) -> None:
    import jsonschema

    schema = json.loads(guard_schema_path().read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
