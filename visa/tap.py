"""HTTP Message Signatures for the Visa Trusted Agent Protocol.

The wire format matches the reference signer
``create_ed25519_signature`` in
https://github.com/visa/trusted-agent-protocol (``tap-agent/agent_app.py``)
and the reference verifier ``buildRFC9421SignatureString`` in
``cdn-proxy/server.js``.

Signature base, with a newline between lines and no trailing newline::

    "@authority": example.com
    "@path": /checkout
    "@signature-params": ("@authority" "@path"); created=1700000000; expires=1700000480; keyId="paycheck-ab"; alg="ed25519"; nonce="..."; tag="agent-payer-auth"

Headers::

    Signature-Input: sig2=<the @signature-params value>
    Signature: sig2=:<standard base64>:

Verification also applies the protocol rules the specification states and
the reference sample enforces in part: both timestamps are required, the
gap between ``created`` and ``expires`` is at most 8 minutes, ``created``
is not in the future, ``expires`` is in the future, a nonce is not reused,
and ``tag`` is ``agent-browser-auth`` or ``agent-payer-auth``.
"""

from __future__ import annotations

import base64
import re
import threading
import time
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from visa.keys import AgentKey, KeyDirectory

TAG_BROWSER = "agent-browser-auth"
TAG_PAYER = "agent-payer-auth"
ALLOWED_TAGS = frozenset({TAG_BROWSER, TAG_PAYER})
MAX_WINDOW_SECONDS = 8 * 60
COVERED = ("@authority", "@path")
ALGORITHM = "ed25519"
LABEL = "sig2"

_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_SIGNATURE_INPUT = re.compile(r"^sig2=\((?P<covered>[^)]*)\);\s*(?P<attrs>.*)$", re.DOTALL)
_ATTRIBUTE = re.compile(r'([A-Za-z][A-Za-z0-9]*)=(?:"([^"]*)"|(-?\d+))')
_SIGNATURE = re.compile(r"^sig2=:([A-Za-z0-9+/=]+):$")


@dataclass(frozen=True)
class SignedRequest:
    """Headers and the values that went into them. No private key material."""

    signature_input: str
    signature: str
    key_id: str
    nonce: str
    tag: str
    alg: str
    created: int
    expires: int
    authority: str
    path: str
    signature_base: str

    def as_http(self) -> dict[str, str]:
        return {
            "Signature-Input": self.signature_input,
            "Signature": self.signature,
        }


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: str
    key_id: str = ""
    nonce: str = ""
    tag: str = ""
    alg: str = ""
    created: int | None = None
    expires: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "key_id": self.key_id,
            "nonce": self.nonce,
            "tag": self.tag,
            "alg": self.alg,
            "created": self.created,
            "expires": self.expires,
        }


def build_signature_base(
    authority: str,
    path: str,
    signature_params: str,
    covered: tuple[str, ...] = COVERED,
) -> str:
    """Build the reference signature base. Component values are not quoted."""

    lines: list[str] = []
    for name in covered:
        if name == "@authority":
            lines.append(f'"@authority": {authority}')
        elif name == "@path":
            lines.append(f'"@path": {path}')
        else:
            raise ValueError(f"unsupported covered component {name}")
    lines.append(f'"@signature-params": {signature_params}')
    return "\n".join(lines)


def sign(
    key: AgentKey,
    *,
    authority: str,
    path: str,
    tag: str,
    created: int | None = None,
    expires: int | None = None,
    nonce: str | None = None,
    now: int | None = None,
) -> SignedRequest:
    """Sign one request with the agent private key and a fresh nonce."""

    if not authority or not path.startswith("/"):
        raise ValueError("authority and an absolute path are required")
    current = int(time.time() if now is None else now)
    created_at = current if created is None else int(created)
    expires_at = created_at + MAX_WINDOW_SECONDS if expires is None else int(expires)
    nonce_value = str(uuid.uuid4()) if nonce is None else nonce
    signature_params = (
        '("@authority" "@path"); '
        f"created={created_at}; expires={expires_at}; "
        f'keyId="{key.key_id}"; alg="{ALGORITHM}"; '
        f'nonce="{nonce_value}"; tag="{tag}"'
    )
    signature_base = build_signature_base(authority, path, signature_params)
    raw_signature = key.private_key.sign(signature_base.encode("utf-8"))
    signature_b64 = base64.b64encode(raw_signature).decode("ascii")
    return SignedRequest(
        signature_input=f"{LABEL}={signature_params}",
        signature=f"{LABEL}=:{signature_b64}:",
        key_id=key.key_id,
        nonce=nonce_value,
        tag=tag,
        alg=ALGORITHM,
        created=created_at,
        expires=expires_at,
        authority=authority,
        path=path,
        signature_base=signature_base,
    )


class NonceCache:
    """Nonces accepted in the last 8 minutes. A repeat is a replay."""

    def __init__(self, ttl_seconds: int = MAX_WINDOW_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[str, int] = {}
        self._lock = threading.Lock()

    def seen(self, nonce: str, now: int) -> bool:
        with self._lock:
            self._purge(now)
            return nonce in self._seen

    def claim(self, nonce: str, now: int) -> bool:
        """Record ``nonce``. Return False when it was already recorded."""

        with self._lock:
            self._purge(now)
            if nonce in self._seen:
                return False
            self._seen[nonce] = now
            return True

    def _purge(self, now: int) -> None:
        cutoff = now - self._ttl
        stale = [nonce for nonce, seen_at in self._seen.items() if seen_at < cutoff]
        for nonce in stale:
            del self._seen[nonce]


def _reject(reason: str, **fields: object) -> VerifyResult:
    return VerifyResult(ok=False, reason=reason, **fields)  # type: ignore[arg-type]


class Verifier:
    """Merchant-side check of a Signed agent check (Visa Trusted Agent Protocol)."""

    def __init__(
        self,
        keys: KeyDirectory,
        *,
        clock=time.time,
        nonces: NonceCache | None = None,
    ) -> None:
        self.keys = keys
        self._clock = clock
        self.nonces = nonces if nonces is not None else NonceCache()

    def verify(
        self,
        *,
        authority: str,
        path: str,
        signature_input: str | None,
        signature: str | None,
        expected_tag: str | None = None,
    ) -> VerifyResult:
        if not signature_input or not signature:
            return _reject("missing Signature-Input or Signature")

        parsed = _parse_signature_input(signature_input)
        if parsed is None:
            return _reject("malformed Signature-Input")
        covered, attributes, signature_params = parsed

        key_id = attributes.get("keyId")
        tag = attributes.get("tag")
        alg = attributes.get("alg")
        nonce = attributes.get("nonce")
        created = attributes.get("created")
        expires = attributes.get("expires")
        partial = {
            "key_id": key_id if isinstance(key_id, str) else "",
            "tag": tag if isinstance(tag, str) else "",
            "alg": alg if isinstance(alg, str) else "",
            "nonce": nonce if isinstance(nonce, str) else "",
            "created": created if isinstance(created, int) else None,
            "expires": expires if isinstance(expires, int) else None,
        }

        if covered != COVERED:
            return _reject(
                "covered components must be @authority and @path",
                **partial,
            )
        missing = [
            name
            for name in ("created", "expires", "keyId", "alg", "nonce", "tag")
            if name not in attributes
        ]
        if missing:
            return _reject(
                "missing required signature field: " + ", ".join(missing),
                **partial,
            )
        if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
            return _reject("keyId is missing or not a token", **partial)
        if not isinstance(tag, str) or tag not in ALLOWED_TAGS:
            return _reject(
                "tag must be agent-browser-auth or agent-payer-auth",
                **partial,
            )
        if not isinstance(alg, str) or alg.lower() != ALGORITHM:
            return _reject("alg must be ed25519", **partial)
        if not isinstance(nonce, str) or not nonce:
            return _reject("nonce is missing", **partial)
        if not isinstance(created, int) or not isinstance(expires, int):
            return _reject("created and expires must be unix seconds", **partial)

        now = int(self._clock())
        if expires - created > MAX_WINDOW_SECONDS or expires <= created:
            return _reject(
                "created and expires must be within 8 minutes",
                **partial,
            )
        if created > now:
            return _reject("created timestamp is in the future", **partial)
        if expires <= now:
            return _reject("signature has expired", **partial)
        if self.nonces.seen(nonce, now):
            return _reject("nonce was already used", **partial)

        public_key = self.keys.get(key_id)
        if public_key is None:
            return _reject("unknown keyId", **partial)

        signature_bytes = _parse_signature(signature)
        if signature_bytes is None:
            return _reject("malformed Signature", **partial)
        signature_base = build_signature_base(
            authority, path, signature_params, covered
        )
        if not _ed25519_ok(public_key, signature_bytes, signature_base):
            return _reject("invalid signature", **partial)

        if expected_tag is not None and tag != expected_tag:
            return _reject(
                f"tag {tag} does not match this route ({expected_tag})",
                **partial,
            )
        if not self.nonces.claim(nonce, now):
            return _reject("nonce was already used", **partial)
        return VerifyResult(ok=True, reason="signature accepted", **partial)


def _parse_signature_input(
    header: str,
) -> tuple[tuple[str, ...], dict[str, str | int], str] | None:
    match = _SIGNATURE_INPUT.fullmatch(header.strip())
    if match is None:
        return None
    covered = tuple(
        part.strip().strip('"')
        for part in match.group("covered").split()
        if part.strip()
    )
    attributes: dict[str, str | int] = {}
    for found in _ATTRIBUTE.finditer(match.group("attrs")):
        name = found.group(1)
        if found.group(2) is not None:
            attributes[name] = found.group(2)
        else:
            attributes[name] = int(found.group(3))
    signature_params = header.strip()[len(f"{LABEL}=") :]
    return covered, attributes, signature_params


def _parse_signature(header: str) -> bytes | None:
    match = _SIGNATURE.fullmatch(header.strip())
    if match is None:
        return None
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except Exception:
        return None
    if len(raw) != 64:
        return None
    return raw


def _ed25519_ok(public_key: Ed25519PublicKey, signature: bytes, base: str) -> bool:
    try:
        public_key.verify(signature, base.encode("utf-8"))
    except InvalidSignature:
        return False
    return True
