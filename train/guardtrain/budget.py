"""Refuse a launch that would cross the Veri cap or drain the balance.

Veri terminates every running job in the workspace when the balance hits $0.
The ledger cap (default $55 of a $60 credit) and a $3 balance floor are both
checked before each launch, against the projected cost of every job still to
start plus what the ledger has already committed.
"""

from __future__ import annotations

from decimal import Decimal

from guardtrain.ledger import SpendCapExceeded, SpendLedger
from guardtrain.schema import VERI_BALANCE_FLOOR_USD, VERI_HARD_CAP_USD


def assert_jobs_fit(
    *,
    ledger: SpendLedger,
    spend_cap: Decimal | str,
    reservations: list[Decimal],
    balance: Decimal | None,
    require_balance: bool,
    floor: Decimal | str = VERI_BALANCE_FLOOR_USD,
) -> dict:
    """Raise ``SpendCapExceeded`` when the remaining jobs do not fit.

    ``reservations`` is every job that is about to start and is not yet an open
    ledger entry. Jobs already reserved are inside ``ledger`` totals.
    """
    projected = sum((Decimal(str(amount)) for amount in reservations), Decimal("0"))
    totals = ledger.totals(spend_cap)
    floor_usd = Decimal(str(floor))
    if totals.committed + projected > totals.cap:
        raise SpendCapExceeded(
            (
                f"Refusing launch: projected ${projected} for {len(reservations)} job(s) "
                f"plus ${totals.committed} already committed would pass the ${totals.cap} cap "
                f"(hard cap ${VERI_HARD_CAP_USD})."
            ),
            spent=totals.committed,
            attempted=projected,
            cap=totals.cap,
        )
    if require_balance and balance is None:
        raise SpendCapExceeded(
            "Refusing launch: veri billing balance did not return a balance. "
            f"The account must keep at least ${floor_usd} so a running job cannot hit $0.",
            spent=totals.committed,
            attempted=projected,
            cap=totals.cap,
        )
    if balance is not None and balance - projected < floor_usd:
        left = balance - projected
        raise SpendCapExceeded(
            (
                f"Refusing launch: projected ${projected} would leave ${left} of the "
                f"${balance} Veri balance, under the ${floor_usd} floor. "
                "Veri kills every running job when the balance reaches $0."
            ),
            spent=totals.committed,
            attempted=projected,
            cap=totals.cap,
        )
    return {
        "spend_cap_usd": format(totals.cap, "f"),
        "balance_floor_usd": format(floor_usd, "f"),
        "balance_usd": None if balance is None else format(balance, "f"),
        "projected_usd": format(projected, "f"),
        "committed_before_usd": format(totals.committed, "f"),
        "jobs": len(reservations),
    }
