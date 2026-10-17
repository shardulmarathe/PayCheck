"""Browser Use shopper for the checkout-guard gym."""

from __future__ import annotations

import os

# The shopper uses the open-source library and a local browser. Do not send
# anonymized product telemetry or sync a Browser Use cloud session unless the
# operator opted in before import.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")
os.environ.setdefault("BROWSER_USE_LOGGING_LEVEL", "warning")

__version__ = "0.1.0"
