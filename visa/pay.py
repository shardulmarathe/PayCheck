"""Guarded payment.

``pay`` calls the guard at ``SURESHOP_CHECK_URL`` first. A block logs the
trick type and evidence and does not call the processor. An allow submits
exactly one payment. A timeout or any other guard error does not call the
processor, and the result says ``guard error`` rather than ``blocked``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

from visa.guard import GuardDecision, GuardError, call_check
from visa.processors import PaymentRequest, PaymentResult, PaymentProcessor

logger = logging.getLogger("visa.pay")


@dataclass(frozen=True)
class PayResult:
    paid: bool
    payment_calls: int
    verdict: str
    attack_type: str
    evidence: str
    instruction: str
    reason: str
    outcome: str
    payment: PaymentResult | None

    def to_dict(self) -> dict[str, object]:
        return {
            "paid": self.paid,
            "payment_calls": self.payment_calls,
            "verdict": self.verdict,
            "attack_type": self.attack_type,
            "evidence": self.evidence,
            "instruction": self.instruction,
            "reason": self.reason,
            "outcome": self.outcome,
            "payment": None if self.payment is None else self.payment.to_dict(),
        }


def pay(
    page: Mapping[str, Any],
    processor: PaymentProcessor,
    *,
    check_url: str | None = None,
) -> PayResult:
    """Check the page, and submit ``processor.charge`` only when the guard allows."""

    try:
        decision = call_check(page, check_url)
    except GuardError as exc:
        reason = f"guard error: {exc}"
        logger.error("payment not sent: %s", reason)
        return PayResult(
            paid=False,
            payment_calls=0,
            verdict="",
            attack_type="",
            evidence="",
            instruction="",
            reason=reason,
            outcome="guard error",
            payment=None,
        )
    if decision.verdict != "allow":
        reason = _block_reason(decision)
        logger.warning("payment not sent: %s", reason)
        return PayResult(
            paid=False,
            payment_calls=0,
            verdict="block",
            attack_type=decision.attack_type,
            evidence=decision.evidence,
            instruction=decision.instruction,
            reason=reason,
            outcome="blocked",
            payment=None,
        )
    result = processor.charge(_payment_for(page))
    return PayResult(
        paid=result.status == "approved",
        payment_calls=1,
        verdict="allow",
        attack_type=decision.attack_type,
        evidence=decision.evidence,
        instruction=decision.instruction,
        reason="guard allowed payment",
        outcome="allowed",
        payment=result,
    )


def _block_reason(decision: GuardDecision) -> str:
    trick = decision.attack_type or "block"
    return (
        f"{trick}. evidence={decision.evidence!r}. "
        f"instruction={decision.instruction!r}"
    )


def _payment_for(page: Mapping[str, Any]) -> PaymentRequest:
    amount = page.get("amount_cents")
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise GuardError("page amount_cents must be a non-negative integer")
    return PaymentRequest(
        amount_cents=amount,
        currency=str(page.get("currency", "USD")),
        order_id=str(page.get("order_id", "")),
        merchant=str(page.get("merchant", "PayCheck")),
        description=str(page.get("description", "PayCheck checkout")),
    )
