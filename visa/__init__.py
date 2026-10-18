"""Signed agent check (Visa Trusted Agent Protocol).

The agent signs HTTP requests. The demo store verifies them. ``pay`` calls
the guard and only then submits a payment.
"""

from visa.keys import AgentKey
from visa.pay import pay
from visa.tap import VerifyResult, Verifier, sign

__all__ = ["AgentKey", "VerifyResult", "Verifier", "pay", "sign"]
