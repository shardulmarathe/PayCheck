"""Client for the SureShop guard's HTTP ``/check`` endpoint."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


class GuardError(Exception):
    """The guard did not return a usable allow or block decision."""


@dataclass(frozen=True)
class GuardDecision:
    verdict: str
    attack_type: str
    evidence: str
    instruction: str

    def to_dict(self) -> dict[str, str]:
        return {
            "verdict": self.verdict,
            "attack_type": self.attack_type,
            "evidence": self.evidence,
            "instruction": self.instruction,
        }


def resolve_check_url(raw: str | None = None) -> str:
    """Return the guard URL. ``SURESHOP_CHECK_URL`` may be the origin or ``/check``."""

    value = raw if raw is not None else os.environ.get("SURESHOP_CHECK_URL", "")
    value = value.strip().rstrip("/")
    if not value:
        raise GuardError("SURESHOP_CHECK_URL is not set")
    if value.endswith("/check"):
        return value
    return value + "/check"


def call_check(
    page: Mapping[str, Any],
    check_url: str | None = None,
    *,
    timeout: float = 5,
) -> GuardDecision:
    """POST the cart or checkout page. Fail closed on any unusable response."""

    url = resolve_check_url(check_url)
    body = json.dumps(guard_payload(page)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise GuardError(f"guard returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GuardError(f"guard check failed: {exc}") from exc
    return parse_decision(payload)


def guard_payload(page: Mapping[str, Any]) -> dict[str, str]:
    """Same body the shopper guard client posts: text, url, action, target."""

    text = page.get("text")
    if text is None:
        text = page.get("html", "")
    return {
        "text": str(text),
        "url": str(page.get("url", "")),
        "action": str(page.get("action", "place_order")),
        "target": str(page.get("target", "")),
    }


def parse_decision(payload: bytes) -> GuardDecision:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GuardError("guard response was not JSON") from exc
    if not isinstance(data, dict):
        raise GuardError("guard response was not a JSON object")
    verdict = data.get("verdict")
    # The gym guard contract says "pass". This step says "allow". Both mean pay.
    if verdict == "pass":
        verdict = "allow"
    if verdict not in ("allow", "block"):
        raise GuardError(f"guard verdict {verdict!r} is not allow or block")
    attack_type = data.get("attack_type", data.get("trick_type", data.get("trick", "")))
    evidence = data.get("evidence", "")
    instruction = data.get("instruction", "")
    if not isinstance(attack_type, str) or not isinstance(evidence, str):
        raise GuardError("guard trick type or evidence was not a string")
    if not isinstance(instruction, str):
        instruction = ""
    return GuardDecision(
        verdict=verdict,
        attack_type=attack_type,
        evidence=evidence,
        instruction=instruction,
    )
