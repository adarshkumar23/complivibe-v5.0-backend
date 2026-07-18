# mypy: allow-untyped-defs
"""Full hash-chain verification for signed decision receipts.

Reuses `verify_receipt` (a module-level, key-free function) from
`receipt_crypto` for each individual receipt's own signature check, and adds
the piece `verify_receipt` deliberately does not do on its own: making sure a
whole *list* of receipts forms one unbroken, correctly-ordered chain (each
receipt's `previous_receipt_hash` pointing at the true `receipt_hash` of the
receipt immediately before it).

Ported verbatim from P3 `core-side-patch/services/receipt_chain.py` (import
made package-relative).

Explicitly-decided behavior:
- An empty list is treated as trivially passing.
- Verification is strictly sequential and stops at the first failure -- once a
  receipt fails, everything after it is of unknown provenance.
- The two failure modes (bad signature vs broken hash link) are reported with
  distinct messages.
"""

from __future__ import annotations

from dataclasses import dataclass

from .receipt_crypto import Receipt, verify_receipt

__all__ = ["ChainVerificationResult", "verify_chain"]


@dataclass(frozen=True)
class ChainVerificationResult:
    passed: bool
    verified_count: int
    failure_index: int | None
    failure_reason: str | None


def verify_chain(receipts: list[Receipt]) -> ChainVerificationResult:
    """Walk `receipts` in order, verifying each receipt's own signature and its
    hash-chain link to the receipt before it. Stops at the first failure.
    """
    if not receipts:
        return ChainVerificationResult(
            passed=True,
            verified_count=0,
            failure_index=None,
            failure_reason=None,
        )

    for i, receipt in enumerate(receipts):
        if i == 0:
            if receipt.previous_receipt_hash is not None:
                return ChainVerificationResult(
                    passed=False,
                    verified_count=0,
                    failure_index=0,
                    failure_reason=(
                        "chain does not start with a receipt whose "
                        "previous_receipt_hash is None (receipt at index 0 "
                        f"has previous_receipt_hash={receipt.previous_receipt_hash!r})"
                    ),
                )
        else:
            previous = receipts[i - 1]
            if receipt.previous_receipt_hash != previous.receipt_hash:
                return ChainVerificationResult(
                    passed=False,
                    verified_count=i,
                    failure_index=i,
                    failure_reason=(
                        f"receipt at index {i}'s previous_receipt_hash does not "
                        f"match receipt at index {i - 1}'s receipt_hash"
                    ),
                )

        if not verify_receipt(receipt):
            return ChainVerificationResult(
                passed=False,
                verified_count=i,
                failure_index=i,
                failure_reason=f"receipt at index {i} has an invalid signature",
            )

    return ChainVerificationResult(
        passed=True,
        verified_count=len(receipts),
        failure_index=None,
        failure_reason=None,
    )
