# mypy: allow-untyped-defs
"""First-party Ed25519 decision-receipt signing + key-free verification.

Replaces P3's dependency on the external `mcp_receipt_governed` package (pinned
as `agentmesh-mcp-receipts==3.7.0`, which is not installable from any public
index). Per PATENT.md 0 and 1.1(4), the *signing* and *hash-chaining* of
receipts are explicitly disclosed as PRIOR ART and are NOT the patent's claim
-- the novel step is the obligation-to-Rego derivation (see
`derivation_engine.py`). So implementing the signing primitive first-party,
rather than via a specific third-party package, does not weaken the patent's
technical basis.

What IS preserved is the substance of dependent Claim 4: a decision receipt is
cryptographically signed with a private Ed25519 key that lives *exclusively*
inside `ReceiptSigner` (meant to run in the customer's own deployment), and
`verify_receipt()` is a module-level, **key-free** function that verifies using
only the *public* key carried on the receipt itself -- so CompliVibe's core can
receive and store a receipt without ever holding the private signing key.

Built directly on `cryptography` (already a core dependency; the same library
`app/services/content_provenance_service.py` uses for Ed25519). The public API
(`Receipt`, `ReceiptSigner`, `verify_receipt`) is kept identical to P3's
`services/receipts.py` so `receipt_chain.py` and `policy_provider.py` port
unchanged.

What is and isn't cryptographically covered
-------------------------------------------
The signed canonical payload covers the receipt's decision, its envelope hash,
its timestamp, its receipt id, and its `previous_receipt_hash` chain link --
but **not** the free-text `reasons` list (descriptive metadata riding alongside
the signed decision). `verify_receipt()` verifies the decision and chain
linkage; it does not and cannot make `reasons` text tamper-evident. Do not
treat `reasons` as an integrity-protected field.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

__all__ = ["Receipt", "ReceiptSigner", "verify_receipt", "canonical_payload"]


@dataclass(frozen=True)
class Receipt:
    """A single signed, chainable decision receipt.

    Field shape kept identical to P3's `services.receipts.Receipt` so the
    chain-verification and policy-provider code depend on a stable contract.
    """

    receipt_id: str
    timestamp: str
    envelope_hash: str
    decision: str
    reasons: list[str]
    previous_receipt_hash: str | None
    signature: str  # hex-encoded Ed25519 signature
    receipt_hash: str  # hex-encoded sha256 of the canonical signed payload
    public_key_hex: str


def canonical_payload(
    *,
    receipt_id: str,
    decision: str,
    envelope_hash: str,
    timestamp: str,
    previous_receipt_hash: str | None,
) -> bytes:
    """Deterministic byte representation of the signed portion of a receipt.

    Deliberately excludes `reasons` (not integrity-protected) and
    `public_key_hex`/`signature`/`receipt_hash` (derived). `previous_receipt_hash`
    is included so tampering with the chain link invalidates both the receipt
    hash and the signature.
    """
    payload = {
        "receipt_id": receipt_id,
        "decision": "allow" if decision == "allow" else "deny",
        "envelope_hash": envelope_hash,
        "timestamp": timestamp,
        "previous_receipt_hash": previous_receipt_hash,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class ReceiptSigner:
    """Holds a private Ed25519 key; the only thing in this module that does.

    Meant to run inside the customer's own deployment, never inside CompliVibe's
    core. `signing_key_hex` is a caller-supplied 32-byte hex seed.
    """

    def __init__(self, signing_key_hex: str) -> None:
        seed = bytes.fromhex(signing_key_hex)
        if len(seed) != 32:
            raise ValueError(
                f"signing_key_hex must decode to exactly 32 bytes, got {len(seed)}"
            )
        self._private_key = Ed25519PrivateKey.from_private_bytes(seed)
        self.public_key_hex = self._private_key.public_key().public_bytes_raw().hex()

    def sign_receipt(
        self,
        *,
        decision: str,
        reasons: list[str],
        envelope_hash: str,
        previous_receipt_hash: str | None,
        timestamp: str,
    ) -> Receipt:
        """Sign a new receipt, chaining it to `previous_receipt_hash` (the prior
        receipt's `receipt_hash`, or `None` if this is the first in a chain).
        """
        receipt_id = str(uuid.uuid4())
        payload = canonical_payload(
            receipt_id=receipt_id,
            decision=decision,
            envelope_hash=envelope_hash,
            timestamp=timestamp,
            previous_receipt_hash=previous_receipt_hash,
        )
        signature = self._private_key.sign(payload).hex()
        receipt_hash = _payload_hash(payload)
        return Receipt(
            receipt_id=receipt_id,
            timestamp=timestamp,
            envelope_hash=envelope_hash,
            decision="allow" if decision == "allow" else "deny",
            reasons=list(reasons),
            previous_receipt_hash=previous_receipt_hash,
            signature=signature,
            receipt_hash=receipt_hash,
            public_key_hex=self.public_key_hex,
        )


def verify_receipt(receipt: Receipt) -> bool:
    """Verify a single receipt's Ed25519 signature and its self-reported
    `receipt_hash`, using only `receipt.public_key_hex` -- a **public** key
    carried on the receipt itself.

    No parameter of this function can ever hold a private key (see module
    docstring and Claim 4). Returns `False` (never raises) for any malformed
    input or bad signature.
    """
    try:
        payload = canonical_payload(
            receipt_id=receipt.receipt_id,
            decision=receipt.decision,
            envelope_hash=receipt.envelope_hash,
            timestamp=receipt.timestamp,
            previous_receipt_hash=receipt.previous_receipt_hash,
        )
        if _payload_hash(payload) != receipt.receipt_hash:
            return False
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(receipt.public_key_hex))
        public_key.verify(bytes.fromhex(receipt.signature), payload)
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
