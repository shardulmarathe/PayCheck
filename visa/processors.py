"""Payment backends.

``MockProcessor`` is the one the demo runs. Its results say ``provenance: mock``.
``VisaSandboxProcessor`` is a stub for the Visa Intelligent Commerce developer
sandbox. It does not open a socket. See ``visa/README.md`` for the credentials
that arm it.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


@dataclass(frozen=True)
class PaymentRequest:
    amount_cents: int
    currency: str
    order_id: str
    merchant: str
    description: str


@dataclass(frozen=True)
class PaymentResult:
    status: str
    provenance: str
    reference: str
    amount_cents: int
    currency: str
    order_id: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class PaymentProcessor(Protocol):
    def charge(self, payment: PaymentRequest) -> PaymentResult:
        """Submit one payment. Callers must not call this unless the guard allowed."""


class MockProcessor:
    """Local stand-in processor. Output is labeled ``provenance: mock``."""

    provenance = "mock"

    def __init__(self) -> None:
        self.payments: list[PaymentRequest] = []

    def charge(self, payment: PaymentRequest) -> PaymentResult:
        self.payments.append(payment)
        return PaymentResult(
            status="approved",
            provenance="mock",
            reference=f"mock-{payment.order_id}",
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            order_id=payment.order_id,
            detail="local mock processor; no card network was contacted",
        )


VISA_SANDBOX_ENV = (
    "VISA_USER_ID",
    "VISA_PASSWORD",
    "VISA_CERT_PATH",
    "VISA_KEY_PATH",
    "VISA_MLE_KEY_ID",
    "VISA_MLE_PRIVATE_KEY_PATH",
    "VISA_MLE_SERVER_CERT_PATH",
)


class VisaSandboxNotConfigured(Exception):
    """Required sandbox credentials are absent. No Visa host was contacted."""

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        names = ", ".join(missing)
        super().__init__(
            "Visa Intelligent Commerce sandbox credentials are missing: " + names
        )


@dataclass(frozen=True)
class VisaSandboxConfig:
    """Credential paths and ids. Secrets stay in the environment, not in this object."""

    base_url: str
    user_id_set: bool
    password_set: bool
    cert_path: str
    key_path: str
    key_passphrase_set: bool
    mle_key_id_set: bool
    mle_private_key_path: str
    mle_server_cert_path: str

    @property
    def configured(self) -> bool:
        return not self.missing()

    def missing(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.user_id_set:
            missing.append("VISA_USER_ID")
        if not self.password_set:
            missing.append("VISA_PASSWORD")
        if not self.mle_key_id_set:
            missing.append("VISA_MLE_KEY_ID")
        for name, path in (
            ("VISA_CERT_PATH", self.cert_path),
            ("VISA_KEY_PATH", self.key_path),
            ("VISA_MLE_PRIVATE_KEY_PATH", self.mle_private_key_path),
            ("VISA_MLE_SERVER_CERT_PATH", self.mle_server_cert_path),
        ):
            candidate = Path(path) if path else None
            if candidate is None or not candidate.is_file() or candidate.stat().st_size == 0:
                missing.append(name)
        host = urlparse(self.base_url).hostname or ""
        if host not in {"sandbox.api.visa.com"}:
            missing.append("VISA_SANDBOX_BASE_URL")
        return tuple(missing)


class VisaSandboxProcessor:
    """Stub adapter for the Visa Intelligent Commerce developer sandbox.

    ``charge`` checks credentials and returns. It does not call Visa.
    A missing credential raises ``VisaSandboxNotConfigured`` before any
    network object is constructed.
    """

    provenance = "visa-sandbox"

    def __init__(self, config: VisaSandboxConfig) -> None:
        self.config = config
        self.network_calls = 0

    @classmethod
    def from_env(cls) -> VisaSandboxProcessor:
        return cls(
            VisaSandboxConfig(
                base_url=os.environ.get(
                    "VISA_SANDBOX_BASE_URL", "https://sandbox.api.visa.com"
                ).strip(),
                user_id_set=bool(os.environ.get("VISA_USER_ID", "").strip()),
                password_set=bool(os.environ.get("VISA_PASSWORD", "").strip()),
                cert_path=os.environ.get("VISA_CERT_PATH", "").strip(),
                key_path=os.environ.get("VISA_KEY_PATH", "").strip(),
                key_passphrase_set=bool(os.environ.get("VISA_KEY_PASSPHRASE", "").strip()),
                mle_key_id_set=bool(os.environ.get("VISA_MLE_KEY_ID", "").strip()),
                mle_private_key_path=os.environ.get("VISA_MLE_PRIVATE_KEY_PATH", "").strip(),
                mle_server_cert_path=os.environ.get("VISA_MLE_SERVER_CERT_PATH", "").strip(),
            )
        )

    def charge(self, payment: PaymentRequest) -> PaymentResult:
        missing = self.config.missing()
        if missing:
            raise VisaSandboxNotConfigured(missing)
        # Credentials are present. This stub still does not transmit.
        return PaymentResult(
            status="not_sent",
            provenance="visa-sandbox",
            reference="",
            amount_cents=payment.amount_cents,
            currency=payment.currency,
            order_id=payment.order_id,
            detail=(
                "credentials are set; this stub does not call the Visa "
                "Intelligent Commerce sandbox"
            ),
        )


def processor_from_env() -> PaymentProcessor:
    """``SURESHOP_PAYMENT_BACKEND=mock`` (default) or ``visa-sandbox``."""

    name = os.environ.get("SURESHOP_PAYMENT_BACKEND", "mock").strip() or "mock"
    if name == "mock":
        return MockProcessor()
    if name == "visa-sandbox":
        return VisaSandboxProcessor.from_env()
    raise ValueError(
        "SURESHOP_PAYMENT_BACKEND must be mock or visa-sandbox, got " + name
    )
