"""Published token prices used for eval cost. Retrieved 2026-10-17.

Local GGUF/Ollama models have no API token price, so their cost is zero while
token counts are still recorded. Stanford-gateway markups are not included;
override the rates with the CLI flags if an invoice disagrees.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from guardtrain.schema import ContractError


@dataclass(frozen=True)
class ModelPrice:
    model: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    source: str
    note: str = ""

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(int(input_tokens)) * self.input_usd_per_mtok / million
            + Decimal(int(output_tokens)) * self.output_usd_per_mtok / million
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "model": self.model,
            "input_usd_per_mtok": format(self.input_usd_per_mtok, "f"),
            "output_usd_per_mtok": format(self.output_usd_per_mtok, "f"),
            "source": self.source,
            "note": self.note,
        }


# Claude Sonnet 5.5 list price: $2 / $10 per million tokens.
# https://platform.claude.com/docs/en/about-claude/pricing
# Gemini 3.1 Pro Preview, prompts <= 200k: $2 / $12 (output includes thinking).
# Gemini 3 Flash Preview: $0.50 / $3.
# https://ai.google.dev/gemini-api/docs/pricing
_PUBLISHED: dict[str, ModelPrice] = {
    "claude-sonnet-5-5": ModelPrice(
        "claude-sonnet-5-5",
        Decimal("2"),
        Decimal("10"),
        "https://platform.claude.com/docs/en/about-claude/pricing",
        "Base input/output. Cache is unused by this runner.",
    ),
    # Opus 5.5 list price, effective ~2026-10-07. The teacher ledger costs cache
    # separately: 5-minute cache write $5/MTok, cache read $0.20/MTok.
    "claude-opus-5-5": ModelPrice(
        "claude-opus-5-5",
        Decimal("4"),
        Decimal("20"),
        "https://platform.claude.com/docs/en/about-claude/pricing",
        "Input $4/MTok, output $20/MTok. Cache write $5/MTok, cache read $0.20/MTok.",
    ),
    "gemini-3.1-pro-preview": ModelPrice(
        "gemini-3.1-pro-preview",
        Decimal("2"),
        Decimal("12"),
        "https://ai.google.dev/gemini-api/docs/pricing",
        "Standard paid tier for prompts <= 200k tokens. Output includes thinking tokens.",
    ),
    "gemini-3-flash-preview": ModelPrice(
        "gemini-3-flash-preview",
        Decimal("0.50"),
        Decimal("3"),
        "https://ai.google.dev/gemini-api/docs/pricing",
        "Text input. Output includes thinking tokens.",
    ),
    "gemini-3.7-flash": ModelPrice(
        "gemini-3.7-flash",
        Decimal("0.75") if date.today() < date(2027, 1, 1) else Decimal("1.50"),
        Decimal("3.75") if date.today() < date(2027, 1, 1) else Decimal("7.50"),
        "https://ai.google.dev/gemini-api/docs/pricing",
        "Introductory rate through 2026-12-31; $1.50 / $7.50 from 2027-01-01. Output includes thinking.",
    ),
    "qwen3-4b": ModelPrice(
        "qwen3-4b",
        Decimal("0"),
        Decimal("0"),
        "local GGUF/Ollama; no published API token price",
        "Untrained Qwen3-4B baseline. Cost is GPU time on your machine, not an API bill.",
    ),
    "qwen3guard-4b": ModelPrice(
        "qwen3guard-4b",
        Decimal("0"),
        Decimal("0"),
        "local GGUF/Ollama; no published API token price",
        "Qwen/Qwen3Guard-Gen-4B baseline.",
    ),
    "mock-guard": ModelPrice(
        "mock-guard",
        Decimal("0"),
        Decimal("0"),
        "offline mock",
        "Keyword mock used to prove the eval harness.",
    ),
}

PRO_GEMINI_MODELS = frozenset({"gemini-3.1-pro-preview"})
LOCAL_MODELS = frozenset({"qwen3-4b", "qwen3guard-4b", "mock-guard"})
OPUS_TEACHER_MODEL = "claude-opus-5-5"
OPUS_CACHE_WRITE_USD_PER_MTOK = Decimal("5")
OPUS_CACHE_READ_USD_PER_MTOK = Decimal("0.20")


def opus_teacher_cost(usage: dict | None) -> Decimal:
    """Bill Opus 5.5 from the usage object, including cache write and cache read.

    ``input_tokens`` excludes cache reads and writes when those fields are set.
    Unknown models are not priced here; the caller must already be Opus 5.5.
    """
    price = lookup_price(OPUS_TEACHER_MODEL)
    payload = usage or {}
    million = Decimal(1_000_000)
    input_tokens = int(payload.get("input_tokens") or 0)
    output_tokens = int(payload.get("output_tokens") or 0)
    cache_write = int(
        payload.get("cache_creation_input_tokens") or payload.get("cache_write_input_tokens") or 0
    )
    cache_read = int(payload.get("cache_read_input_tokens") or 0)
    return (
        Decimal(input_tokens) * price.input_usd_per_mtok
        + Decimal(output_tokens) * price.output_usd_per_mtok
        + Decimal(cache_write) * OPUS_CACHE_WRITE_USD_PER_MTOK
        + Decimal(cache_read) * OPUS_CACHE_READ_USD_PER_MTOK
    ) / million


def gemini_max_tokens(model: str, requested: int | None) -> int:
    """Pro thinking tokens count against the output cap, so the default is 1024."""
    if requested is not None:
        return requested
    if model in PRO_GEMINI_MODELS:
        return 1024
    return 256


def lookup_price(
    model: str,
    *,
    input_usd_per_mtok: str | None = None,
    output_usd_per_mtok: str | None = None,
) -> ModelPrice:
    if input_usd_per_mtok is not None or output_usd_per_mtok is not None:
        if input_usd_per_mtok is None or output_usd_per_mtok is None:
            raise ContractError("Pass both --input-usd-per-mtok and --output-usd-per-mtok.")
        return ModelPrice(
            model,
            Decimal(input_usd_per_mtok),
            Decimal(output_usd_per_mtok),
            "cli override",
            "Overrides the published rate. The spend cap still applies to this rate.",
        )
    key = model.strip()
    if key not in _PUBLISHED:
        known = ", ".join(sorted(_PUBLISHED))
        raise ContractError(
            f"No published price for {key!r}. Refusing to price it at $0. "
            f"Known models: {known}. Or pass both token-price flags."
        )
    return _PUBLISHED[key]
