"""Strip credentials before anything is printed or written."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

_PATTERNS = (
    re.compile(r"vk_" + r"[A-Za-z0-9_\-]{4,}", re.IGNORECASE),
    re.compile(r"sk-" + r"ant-" + r"[A-Za-z0-9_\-]{4,}", re.IGNORECASE),
    re.compile(r"sk-" + r"[A-Za-z0-9]{16,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]{8,}=*"),
    re.compile(
        r"(?i)\b(api[_-]?key|authorization|x-api-key|"
        r"VERI_API_KEY|ANTHROPIC_API_KEY|GEMINI_API_KEY)"
        r"\s*[=:]\s*\S+"
    ),
)


def redact(text: str | None) -> str:
    if not text:
        return ""
    out = str(text)
    for pattern in _PATTERNS:
        out = pattern.sub("[redacted]", out)
    return out


def redact_url(url: str) -> str:
    """Keep the host, drop query strings that might carry tokens."""
    if not url:
        return ""
    parts = urlsplit(url)
    if parts.query or parts.password:
        return urlunsplit((parts.scheme, parts.hostname or parts.netloc, parts.path, "redacted", ""))
    return redact(url)
