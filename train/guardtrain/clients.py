"""Guard clients. Paid SDKs are imported only when a live call is made."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import httpx

from guardtrain.parse import parse_guard_output
from guardtrain.prompts import build_messages, estimate_tokens
from guardtrain.redact import redact, redact_url
from guardtrain.schema import LabelRow


class MissingKeyError(Exception):
    pass


class ApiCallError(Exception):
    def __init__(self, message: str, *, sent: bool):
        super().__init__(message)
        self.sent = sent


@dataclass
class CheckResult:
    verdict: str
    attack_type: str
    evidence: str
    instruction: str
    parse_ok: bool
    raw: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    error: str = ""
    sent: bool = True
    adapter: str = "json"

    def as_pred(self) -> dict:
        return {
            "verdict": self.verdict,
            "attack_type": self.attack_type,
            "evidence": self.evidence,
            "instruction": self.instruction,
            "parse_ok": self.parse_ok,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "raw": self.raw,
            "error": self.error,
            "adapter": self.adapter,
        }


def _from_parsed(parsed, *, input_tokens: int, output_tokens: int, latency_ms: float, sent: bool = True) -> CheckResult:
    return CheckResult(
        verdict=parsed.verdict,
        attack_type=parsed.attack_type,
        evidence=parsed.evidence,
        instruction=parsed.instruction,
        parse_ok=parsed.parse_ok,
        raw=parsed.raw,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        sent=sent,
        adapter=parsed.adapter,
    )


_MOCK_RULES = (
    ("service fee", "hidden_fees", "service fee"),
    ("pre-checked", "preselected_addon", "pre-checked"),
    ("price went up", "price_change", "price went up"),
    ("free trial", "subscription_trap", "free trial"),
    ("card to verify", "fake_card_verification", "card to verify"),
    ("copycat.example", "copycat_domain", "copycat.example"),
    ("injected listing", "listing_injection", "injected listing"),
)


def mock_raw(page_text: str) -> str:
    lowered = page_text.casefold()
    for needle, attack, quote in _MOCK_RULES:
        if needle in lowered:
            obj = {
                "verdict": "block",
                "attack_type": attack,
                "evidence": quote,
                "instruction": "Stop and avoid this checkout trick.",
            }
            return json.dumps(obj)
    return json.dumps(
        {
            "verdict": "pass",
            "attack_type": "none",
            "evidence": "",
            "instruction": "",
        }
    )


def check_mock(row: LabelRow, *, max_page_tokens: int = 2000) -> CheckResult:
    started = time.perf_counter()
    messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
    raw = mock_raw(row.page_text)
    parsed = parse_guard_output(raw, adapter="json")
    latency = (time.perf_counter() - started) * 1000
    in_tok = sum(estimate_tokens(message["content"]) for message in messages)
    out_tok = estimate_tokens(raw)
    return _from_parsed(parsed, input_tokens=in_tok, output_tokens=out_tok, latency_ms=latency, sent=False)


def require_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise MissingKeyError(
            f"{name} is not set. Export it in the environment of the machine that runs this command."
        )
    return value


def _usage_output(completion_tokens: int, reasoning_tokens: int) -> int:
    # OpenAI-style usage usually includes reasoning inside completion_tokens.
    # If reasoning is reported separately and is larger, add it once.
    if reasoning_tokens > completion_tokens:
        return completion_tokens + reasoning_tokens
    return completion_tokens


def gemini_create_kwargs(*, model: str, messages: list[dict], max_tokens: int, thinking_level: str) -> dict:
    # reasoning_effort is the OpenAI-compat spelling of thinking_level.
    # Do not also send thinking_config: Google's compat layer returns 400 if both are set.
    # Temperature is omitted; some Gemini 3 endpoints reject sampling overrides.
    return {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "reasoning_effort": thinking_level,
    }


def check_gemini(
    row: LabelRow,
    *,
    model: str,
    max_tokens: int,
    thinking_level: str,
    max_page_tokens: int,
    create_fn,
) -> CheckResult:
    messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
    kwargs = gemini_create_kwargs(
        model=model, messages=messages, max_tokens=max_tokens, thinking_level=thinking_level
    )
    started = time.perf_counter()
    try:
        response = create_fn(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise ApiCallError(redact(str(exc)), sent=True) from None
    latency = (time.perf_counter() - started) * 1000
    content = response.choices[0].message.content or ""
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and not part.get("thought"):
                parts.append(str(part.get("text") or ""))
        content = "\n".join(parts)
    parsed = parse_guard_output(content or "", adapter="json")
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    details = getattr(usage, "completion_tokens_details", None)
    reasoning = 0
    if isinstance(details, dict):
        reasoning = int(details.get("reasoning_tokens") or 0)
    elif details is not None:
        reasoning = int(getattr(details, "reasoning_tokens", 0) or 0)
    return _from_parsed(
        parsed,
        input_tokens=prompt,
        output_tokens=_usage_output(completion, reasoning),
        latency_ms=latency,
    )


def default_gemini_create():
    require_env("GEMINI_API_KEY")
    base = require_env("GEMINI_BASE_URL")
    from openai import OpenAI

    # max_retries=0: a retried request would be billed again and the ledger only reserved once.
    client = OpenAI(
        base_url=base,
        api_key=os.environ["GEMINI_API_KEY"],
        max_retries=0,
    )
    return client.chat.completions.create, redact_url(base)


def anthropic_create_kwargs(*, model: str, system: str, user: str, max_tokens: int, effort: str) -> dict:
    # Sonnet 5.5 rejects temperature, top_p, and thinking budgets. Effort is the thinking control.
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort},
    }


def _anthropic_text(response) -> str:
    parts = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "\n".join(parts)


def check_anthropic(
    row: LabelRow,
    *,
    model: str,
    max_tokens: int,
    effort: str,
    max_page_tokens: int,
    create_fn,
) -> CheckResult:
    messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
    system = ""
    user = ""
    for message in messages:
        if message["role"] == "system":
            system = message["content"]
        elif message["role"] == "user":
            user = message["content"]
    kwargs = anthropic_create_kwargs(
        model=model, system=system, user=user, max_tokens=max_tokens, effort=effort
    )
    started = time.perf_counter()
    try:
        response = create_fn(**kwargs)
    except Exception as exc:  # noqa: BLE001
        raise ApiCallError(redact(str(exc)), sent=True) from None
    latency = (time.perf_counter() - started) * 1000
    parsed = parse_guard_output(_anthropic_text(response), adapter="json")
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "input_tokens", 0) or 0)
    completion = int(getattr(usage, "output_tokens", 0) or 0)
    cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    # input_tokens on the Claude API excludes cache reads and writes when those fields are set.
    return _from_parsed(
        parsed,
        input_tokens=prompt + cache_read + cache_write,
        output_tokens=completion,
        latency_ms=latency,
    )


def default_anthropic_create():
    require_env("ANTHROPIC_API_KEY")
    from anthropic import Anthropic

    client = Anthropic(max_retries=0)
    return client.messages.create


def check_ollama(
    row: LabelRow,
    *,
    model: str,
    base_url: str,
    max_page_tokens: int,
    adapter: str,
    num_predict: int = 512,
    client: httpx.Client | None = None,
) -> CheckResult:
    messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
    started = time.perf_counter()
    own = client is None
    http = client or httpx.Client(timeout=180)
    try:
        response = http.post(
            base_url.rstrip("/") + "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_predict": num_predict},
            },
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiCallError(redact(str(exc)), sent=True) from None
    finally:
        if own:
            http.close()
    latency = (time.perf_counter() - started) * 1000
    content = ((payload.get("message") or {}).get("content")) or ""
    parsed = parse_guard_output(content, adapter=adapter)
    return _from_parsed(
        parsed,
        input_tokens=int(payload.get("prompt_eval_count") or 0),
        output_tokens=int(payload.get("eval_count") or 0),
        latency_ms=latency,
    )


def check_openai_compat(
    row: LabelRow,
    *,
    model: str,
    base_url: str,
    max_page_tokens: int,
    adapter: str,
    max_tokens: int = 512,
    client: httpx.Client | None = None,
) -> CheckResult:
    """llama.cpp server, or our own /check is separate. This is /v1/chat/completions."""
    messages = build_messages(row, max_page_tokens=max_page_tokens, include_assistant=False)
    started = time.perf_counter()
    own = client is None
    http = client or httpx.Client(timeout=180)
    url = base_url.rstrip("/") + "/chat/completions"
    try:
        response = http.post(
            url,
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        raise ApiCallError(redact(str(exc)), sent=True) from None
    finally:
        if own:
            http.close()
    latency = (time.perf_counter() - started) * 1000
    content = payload["choices"][0]["message"]["content"]
    parsed = parse_guard_output(content or "", adapter=adapter)
    usage = payload.get("usage") or {}
    return _from_parsed(
        parsed,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        latency_ms=latency,
    )


def check_http_endpoint(
    row: LabelRow,
    *,
    url: str,
    client: httpx.Client | None = None,
) -> CheckResult:
    """POST page text to the FastAPI /check endpoint."""
    started = time.perf_counter()
    own = client is None
    http = client or httpx.Client(timeout=180)
    try:
        response = http.post(
            url,
            json={"page_text": row.page_text, "page_id": row.page_id, "store": row.store},
        )
        status = response.status_code
        body = response.content
    except Exception as exc:  # noqa: BLE001
        raise ApiCallError(redact(str(exc)), sent=True) from None
    finally:
        if own:
            http.close()
    latency = (time.perf_counter() - started) * 1000
    if status == 422:
        parsed = parse_guard_output("", adapter="json")
        return _from_parsed(parsed, input_tokens=0, output_tokens=0, latency_ms=latency)
    try:
        if status >= 400:
            raise ApiCallError(redact(f"HTTP {status}"), sent=True)
        payload = json.loads(body)
    except ApiCallError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ApiCallError(redact(str(exc)), sent=True) from None
    parsed = parse_guard_output(json.dumps(payload), adapter="json")
    usage = payload.get("usage") or {}
    return _from_parsed(
        parsed,
        input_tokens=int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or usage.get("completion_tokens") or 0),
        latency_ms=latency,
    )
