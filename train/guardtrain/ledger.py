"""Persistent spend ledgers. A job that would cross the cap is not launched."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from guardtrain.schema import CHECKPOINT_STORAGE_USD, L4_LISTED_USD_PER_HOUR

try:
    import fcntl
except ImportError:  # pragma: no cover - Linux is the supported host
    fcntl = None  # type: ignore


class SpendCapExceeded(Exception):
    def __init__(self, message: str, *, spent: Decimal, attempted: Decimal, cap: Decimal):
        super().__init__(message)
        self.spent = spent
        self.attempted = attempted
        self.cap = cap


def _cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _micro(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


def wall_clock_reservation_usd(
    minutes: int | float,
    gpu_count: int = 1,
    hourly_rate: str | Decimal = L4_LISTED_USD_PER_HOUR,
) -> Decimal:
    """Worst-case Veri bill for a job we will cancel at ``minutes``.

    The listed L4 rate is $1.05/GPU-hour (exact card rate $1.0462). Veri's own
    estimate is GPU time only; every billed job also pays about $0.24 of
    checkpoint storage. Both are included here.
    """
    rate = Decimal(str(hourly_rate))
    gpu = rate * Decimal(str(minutes)) / Decimal(60) * Decimal(int(gpu_count))
    return _cents(gpu + Decimal(CHECKPOINT_STORAGE_USD))


def reserve_for_job(estimate_gpu_usd: Decimal | None, wall_usd: Decimal) -> Decimal:
    """Reserve the larger of the wall-clock cap and Veri's GPU estimate plus storage."""
    if estimate_gpu_usd is None:
        return _cents(wall_usd)
    with_storage = _cents(Decimal(estimate_gpu_usd) + Decimal(CHECKPOINT_STORAGE_USD))
    return max(with_storage, _cents(wall_usd))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def shared_guard_dir() -> Path:
    """One directory for every checkout. The spend caps are process-wide, not per clone."""
    return Path.home() / ".guardgym"


def shared_veri_ledger_path() -> Path:
    return shared_guard_dir() / "veri_spend_ledger.json"


def shared_teacher_ledger_path() -> Path:
    return shared_guard_dir() / "anthropic_teacher_ledger.json"


def shared_teacher_cache_dir() -> Path:
    return shared_guard_dir() / "anthropic_teacher_cache"


@dataclass
class LedgerTotals:
    cap: Decimal
    settled: Decimal
    reserved: Decimal

    @property
    def committed(self) -> Decimal:
        return self.settled + self.reserved

    @property
    def remaining(self) -> Decimal:
        return self.cap - self.committed


class SpendLedger:
    """File ledger.

    ``quant`` is ``cents`` for Veri (bills round to the cent) and ``micro`` for
    token APIs. Open reservations count against the cap until settled or released.
    """

    def __init__(self, path: Path, hard_cap: Decimal | str, *, quant: str = "cents"):
        self.path = Path(path)
        self.hard_cap = Decimal(str(hard_cap))
        if quant not in {"cents", "micro"}:
            raise ValueError("quant must be cents or micro")
        self.quant = quant
        self._round = _cents if quant == "cents" else _micro

    def _empty(self) -> dict:
        return {
            "hard_cap_usd": format(self._round(self.hard_cap), "f"),
            "quant": self.quant,
            "entries": [],
        }

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text())
        stored = Decimal(str(data.get("hard_cap_usd", self.hard_cap)))
        if stored > self.hard_cap:
            data["hard_cap_usd"] = format(self._round(self.hard_cap), "f")
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    @contextmanager
    def _locked(self) -> Iterator[dict]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a+") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                data = self._load()
                yield data
                self._save(data)
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _cap_of(self, data: dict, requested: Decimal | None) -> Decimal:
        stored = Decimal(str(data.get("hard_cap_usd", self.hard_cap)))
        cap = min(stored, self.hard_cap)
        if requested is not None:
            req = Decimal(str(requested))
            if req > self.hard_cap:
                raise SpendCapExceeded(
                    f"Refusing spend cap ${req} above the hard cap ${self.hard_cap}.",
                    spent=Decimal("0"),
                    attempted=req,
                    cap=self.hard_cap,
                )
            cap = min(cap, req)
        return cap

    def _totals(self, data: dict, cap: Decimal) -> LedgerTotals:
        settled = Decimal("0")
        reserved = Decimal("0")
        for entry in data["entries"]:
            status = entry["status"]
            if status == "settled":
                settled += Decimal(str(entry["actual_usd"]))
            elif status == "open":
                reserved += Decimal(str(entry["amount_usd"]))
        return LedgerTotals(cap=cap, settled=settled, reserved=reserved)

    def totals(self, requested_cap: Decimal | str | None = None) -> LedgerTotals:
        data = self._load()
        cap = self._cap_of(data, None if requested_cap is None else Decimal(str(requested_cap)))
        return self._totals(data, cap)

    def would_exceed(self, amount: Decimal | str, requested_cap: Decimal | str | None = None) -> bool:
        totals = self.totals(requested_cap)
        return totals.committed + self._round(Decimal(str(amount))) > totals.cap

    def authorize(
        self,
        amount: Decimal | str,
        *,
        note: str,
        requested_cap: Decimal | str | None = None,
        job_id: str = "",
    ) -> str:
        amount = self._round(Decimal(str(amount)))
        with self._locked() as data:
            cap = self._cap_of(data, None if requested_cap is None else Decimal(str(requested_cap)))
            totals = self._totals(data, cap)
            if totals.committed + amount > cap:
                raise SpendCapExceeded(
                    (
                        f"Refusing to spend ${amount}: the ledger has "
                        f"${totals.committed} committed against a ${cap} cap."
                    ),
                    spent=totals.committed,
                    attempted=amount,
                    cap=cap,
                )
            entry_id = uuid4().hex[:16]
            data["entries"].append(
                {
                    "id": entry_id,
                    "status": "open",
                    "amount_usd": format(amount, "f"),
                    "actual_usd": None,
                    "job_id": job_id,
                    "note": note,
                    "created_at": _now(),
                    "settled_at": None,
                }
            )
            return entry_id

    def _find(self, data: dict, entry_id: str) -> dict:
        for entry in data["entries"]:
            if entry["id"] == entry_id:
                return entry
        raise KeyError(entry_id)

    def settle(self, entry_id: str, actual: Decimal | str, *, job_id: str = "") -> None:
        actual_q = self._round(Decimal(str(actual)))
        with self._locked() as data:
            entry = self._find(data, entry_id)
            entry["status"] = "settled"
            entry["actual_usd"] = format(actual_q, "f")
            if job_id:
                entry["job_id"] = job_id
            entry["settled_at"] = _now()

    def release(self, entry_id: str, *, note: str = "") -> None:
        with self._locked() as data:
            entry = self._find(data, entry_id)
            entry["status"] = "released"
            entry["actual_usd"] = "0"
            if note:
                entry["note"] = (entry.get("note") or "") + " " + note
            entry["settled_at"] = _now()

    def attach_job(self, entry_id: str, job_id: str) -> None:
        with self._locked() as data:
            entry = self._find(data, entry_id)
            entry["job_id"] = job_id

    def public_view(self, requested_cap: Decimal | str | None = None) -> dict:
        data = self._load()
        cap = self._cap_of(data, None if requested_cap is None else Decimal(str(requested_cap)))
        totals = self._totals(data, cap)
        entries = []
        for entry in data["entries"]:
            entries.append(
                {
                    "id": entry["id"],
                    "status": entry["status"],
                    "amount_usd": entry["amount_usd"],
                    "actual_usd": entry["actual_usd"],
                    "job_id": entry.get("job_id") or "",
                    "note": entry.get("note") or "",
                    "created_at": entry.get("created_at"),
                }
            )
        return {
            "path": str(self.path),
            "hard_cap_usd": format(self.hard_cap, "f"),
            "effective_cap_usd": format(cap, "f"),
            "settled_usd": format(totals.settled, "f"),
            "reserved_usd": format(totals.reserved, "f"),
            "committed_usd": format(totals.committed, "f"),
            "remaining_usd": format(totals.remaining, "f"),
            "entries": entries,
        }
