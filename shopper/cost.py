"""Anthropic token spend for the shopper model.

Rates are the public Claude Haiku 5.5 list prices used as a conservative cap:
$0.10 per million input tokens and $0.50 per million output tokens. Cached
prompt tokens are charged at the full input rate so the cap cannot under-count.
"""

from __future__ import annotations

INPUT_USD_PER_MTOK = 0.10
OUTPUT_USD_PER_MTOK = 0.50


class CostCapExceeded(RuntimeError):
    """Raised when the next model call would start past the cap."""

    def __init__(self, usd: float, max_usd: float) -> None:
        self.usd = usd
        self.max_usd = max_usd
        super().__init__(f"shopper spend ${usd:.4f} reached the ${max_usd:.4f} cap")


class CostLedger:
    def __init__(self, max_usd: float) -> None:
        if max_usd < 0:
            raise ValueError("max_usd must be >= 0")
        self.max_usd = float(max_usd)
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.usd = 0.0
        self.tripped = False

    def add_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        prompt = max(0, int(prompt_tokens))
        completion = max(0, int(completion_tokens))
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.usd = (
            self.prompt_tokens * INPUT_USD_PER_MTOK + self.completion_tokens * OUTPUT_USD_PER_MTOK
        ) / 1_000_000

    def add_usage(self, usage) -> None:
        if usage is None:
            return
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        self.add_tokens(prompt, completion)

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
        self.ledger.add_usage(getattr(result, "usage", None))
        return result
