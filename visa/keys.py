"""Runtime Ed25519 agent keys.

Private keys stay in process memory. Nothing in this module writes a key
file, and the repr of an agent key does not include key material.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


@dataclass
class AgentKey:
    """One Ed25519 key the agent signs with and the store verifies against."""

    key_id: str
    private_key: Ed25519PrivateKey
    public_key_b64: str

    def __repr__(self) -> str:
        return f"AgentKey(key_id={self.key_id!r})"

    @classmethod
    def generate(cls, key_id: str | None = None) -> AgentKey:
        private_key = Ed25519PrivateKey.generate()
        raw_public = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        if key_id is None:
            key_id = "sureshop-" + raw_public[:8].hex()
        return cls(
            key_id=key_id,
            private_key=private_key,
            public_key_b64=base64.b64encode(raw_public).decode("ascii"),
        )

    def public_key(self) -> Ed25519PublicKey:
        raw = base64.b64decode(self.public_key_b64)
        return Ed25519PublicKey.from_public_bytes(raw)


class KeyDirectory:
    """In-memory stand-in for the protocol's public key directory.

    The reference merchant fetches a public key by ``keyId``. This demo
    registers the runtime public key instead of reading a key file.
    """

    def __init__(self) -> None:
        self._keys: dict[str, Ed25519PublicKey] = {}

    def register(self, key: AgentKey) -> None:
        self._keys[key.key_id] = key.public_key()

    def get(self, key_id: str) -> Ed25519PublicKey | None:
        return self._keys.get(key_id)
