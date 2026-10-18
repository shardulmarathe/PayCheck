"""Anthropic token spend for the shopper model.

Rates are the public Claude Haiku 5.5 list prices. Prompts of 100K tokens or
fewer are $0.10 / $0.50 per million input / output tokens. Longer prompts are
$0.50 / $2.50. Cache-write tokens are 1.25× the input rate ($0.125, or $0.625
past 100K). Cache reads sit inside browser-use's prompt_tokens and are charged
at the full input rate so the cap cannot under-count.

Spend is cumulative across invocations. The ledger file is the running total
``--max-usd`` checks, unless ``--reset-ledger`` zeroes it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

INPUT_USD_PER_MTOK = 0.10
OUTPUT_USD_PER_MTOK = 0.50
CACHE_WRITE_USD_PER_MTOK = 0.125
LONG_CONTEXT_TOKENS = 100_000
LONG_INPUT_USD_PER_MTOK = 0.50
LONG_OUTPUT_USD_PER_MTOK = 2.50
LONG_CACHE_WRITE_USD_PER_MTOK = 0.625


class CostCapExceeded(RuntimeError):
    """Raised when the next model call would start past the cap."""

    def __init__(self, usd: float, max_usd: float) -> None:
        self.usd = usd
        self.max_usd = max_usd
        super().__init__(f"shopper spend ${usd:.4f} reached the ${max_usd:.4f} cap")


def _int_field(usage, name: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        value = usage.get(name)
    else:
        value = getattr(usage, name, None)
    if value is None:
        return 0
    return max(0, int(value))


def cache_write_tokens(usage, raw=None) -> int:
    """Cache-write tokens, including the raw Anthropic usage when browser-use drops them.

    ``prompt_cache_creation_tokens`` is the total when the SDK filled it in.
    Otherwise the 5-minute and 1-hour breakdown is the total, not an extra copy.
    """
    creation = _int_field(usage, "prompt_cache_creation_tokens")
    if creation:
        return creation
    breakdown = _int_field(usage, "prompt_cache_creation_5m_tokens") + _int_field(
        usage, "prompt_cache_creation_1h_tokens"
    )
    if breakdown:
        return breakdown
    raw_usage = None
    if raw is not None:
        raw_usage = getattr(raw, "usage", None)
        if raw_usage is None and isinstance(raw, dict):
            raw_usage = raw.get("usage")
        if raw_usage is None:
            raw_usage = getattr(raw, "response", None)
            if raw_usage is not None:
                raw_usage = getattr(raw_usage, "usage", None)
    if raw_usage is None:
        return 0
    direct = _int_field(raw_usage, "cache_creation_input_tokens")
    if direct:
        return direct
    nested = raw_usage.get("cache_creation") if isinstance(raw_usage, dict) else getattr(raw_usage, "cache_creation", None)
    if nested is None:
        return 0
    return _int_field(nested, "ephemeral_5m_input_tokens") + _int_field(nested, "ephemeral_1h_input_tokens")


class CostLedger:
    def __init__(self, max_usd: float, path: Path | None = None) -> None:
        if max_usd < 0:
            raise ValueError("max_usd must be >= 0")
        self.max_usd = float(max_usd)
        self.path = Path(path) if path is not None else None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cache_write_tokens = 0
        self.usd = 0.0
        self.tripped = False
        if self.path is not None and self.path.is_file():
            self._load()

    def _load(self) -> None:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.prompt_tokens = int(payload.get("prompt_tokens") or 0)
        self.completion_tokens = int(payload.get("completion_tokens") or 0)
        self.cache_write_tokens = int(payload.get("cache_write_tokens") or 0)
        self.usd = float(payload.get("usd") or 0)

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "usd": round(self.usd, 6),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        }
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cache_write_tokens = 0
        self.usd = 0.0
        self.tripped = False
        self.save()

    def add_call(self, prompt_tokens: int, completion_tokens: int, cache_write_tokens: int = 0) -> None:
        """Price one model call. The long-context rate applies when that call's prompt is over 100K."""
        prompt = max(0, int(prompt_tokens))
        completion = max(0, int(completion_tokens))
        cache_write = max(0, int(cache_write_tokens))
        long = (prompt + cache_write) > LONG_CONTEXT_TOKENS
        input_rate = LONG_INPUT_USD_PER_MTOK if long else INPUT_USD_PER_MTOK
        output_rate = LONG_OUTPUT_USD_PER_MTOK if long else OUTPUT_USD_PER_MTOK
        cache_rate = LONG_CACHE_WRITE_USD_PER_MTOK if long else CACHE_WRITE_USD_PER_MTOK
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cache_write_tokens += cache_write
        self.usd += (prompt * input_rate + completion * output_rate + cache_write * cache_rate) / 1_000_000
        self.save()

    def add_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.add_call(prompt_tokens, completion_tokens, 0)

    def add_usage(self, usage, raw=None) -> None:
        if usage is None and raw is None:
            return
        prompt = _int_field(usage, "prompt_tokens")
        completion = _int_field(usage, "completion_tokens")
        self.add_call(prompt, completion, cache_write_tokens(usage, raw))

    @property
    def exceeded(self) -> bool:
        return self.usd >= self.max_usd

    def before_call(self) -> None:
        if self.exceeded:
            self.tripped = True
            raise CostCapExceeded(self.usd, self.max_usd)


class BudgetedLLM:
    """Delegates to a browser-use chat model and records token spend."""

    def __init__(self, inner, ledger: CostLedger) -> None:
        self.inner = inner
        self.ledger = ledger
        self.model = inner.model

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    async def ainvoke(self, messages, output_format=None, **kwargs):
        self.ledger.before_call()
        if output_format is None:
            result = await self.inner.ainvoke(messages, **kwargs)
        else:
            result = await self.inner.ainvoke(messages, output_format, **kwargs)
        raw = getattr(result, "response", None)
        self.ledger.add_usage(getattr(result, "usage", None), raw=raw if raw is not None else result)
        return result
