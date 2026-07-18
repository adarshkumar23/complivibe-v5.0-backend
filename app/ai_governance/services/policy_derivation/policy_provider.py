# mypy: allow-untyped-defs
"""CompliVibePolicyProvider: this feature's external-policy-backend adapter.

Thin glue: it builds a safe envelope from a raw action, asks OPA for a
decision, asks the caller-supplied signer (if any) to produce a chained
receipt, and returns a decision result plus enough detail to log a check event.
It does not intercept actions, does not evaluate Rego itself (that's OpaClient
talking to a separately-deployed OPA), and does not hold a signing key (that's
the `sign_receipt_fn`, meant to run in the customer's own deployment).

Ported verbatim from P3 `core-side-patch/services/policy_provider.py` (imports
made package-relative).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol

from .envelope import ActionEnvelope, build_envelope
from .opa_client import OpaClient
from .receipt_crypto import Receipt

__all__ = [
    "PolicyDecisionResult",
    "CheckActionResult",
    "CompliVibePolicyProvider",
]


@dataclass(frozen=True)
class PolicyDecisionResult:
    allowed: bool
    reason: str
    backend: str
    latency_ms: float
    raw_response: Any = None


@dataclass(frozen=True)
class CheckActionResult:
    decision: PolicyDecisionResult
    envelope: ActionEnvelope
    receipt: Receipt | None


class _SupportsSignReceipt(Protocol):
    def __call__(
        self,
        *,
        decision: str,
        reasons: list[str],
        envelope_hash: str,
        previous_receipt_hash: str | None,
        timestamp: str,
    ) -> Receipt: ...


class CompliVibePolicyProvider:
    """Implements the enforcement runtime's `ExternalPolicyBackend` structural
    protocol: a `name` property, `evaluate(action, context)`, and `healthy()`.

    Receipt signing is optional and deliberately not owned here. If no signer is
    supplied, `evaluate()` still returns a decision; it just skips receipt
    creation, since CompliVibe's core has no signing key of its own.
    """

    def __init__(
        self,
        opa_client: OpaClient,
        rego_package: str,
        sign_receipt_fn: _SupportsSignReceipt | None = None,
        previous_receipt_hash: str | None = None,
    ) -> None:
        self._opa_client = opa_client
        self._rego_package = rego_package
        self._sign_receipt_fn = sign_receipt_fn
        self._previous_receipt_hash = previous_receipt_hash
        self._chain_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "complivibe-derived-guardrail"

    def evaluate(self, action: str, context: dict) -> PolicyDecisionResult:
        opa_decision = self._opa_client.evaluate(package=self._rego_package, input_data=context)
        reason = "" if opa_decision.allowed else (opa_decision.error or "denied by policy")
        return PolicyDecisionResult(
            allowed=opa_decision.allowed,
            reason=reason,
            backend=self.name,
            latency_ms=opa_decision.evaluation_ms,
            raw_response=opa_decision.raw_result,
        )

    def close(self) -> None:
        self._opa_client.close()

    def __enter__(self) -> "CompliVibePolicyProvider":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def healthy(self) -> bool:
        probe = self._opa_client.evaluate(package=self._rego_package, input_data={})
        return probe.source == "opa"

    def check_action(self, raw_action: dict, *, timestamp: str) -> CheckActionResult:
        """Build a safe envelope from the raw action (rejecting any
        payload-shaped fields), evaluate it, and -- if a signer was configured
        -- produce a chained receipt.
        """
        envelope = build_envelope(raw_action)
        # compile_constraint_spec generates Rego that reads `input.action.<field>`,
        # so the envelope must be nested under an "action" key here.
        context = {"action": envelope.model_dump()}
        decision = self.evaluate(action=envelope.action_type, context=context)

        receipt: Receipt | None = None
        if self._sign_receipt_fn is not None:
            envelope_hash = _hash_envelope(envelope)
            reasons = [decision.reason] if decision.reason else []
            with self._chain_lock:
                receipt = self._sign_receipt_fn(
                    decision="allow" if decision.allowed else "deny",
                    reasons=reasons,
                    envelope_hash=envelope_hash,
                    previous_receipt_hash=self._previous_receipt_hash,
                    timestamp=timestamp,
                )
                self._previous_receipt_hash = receipt.receipt_hash

        return CheckActionResult(decision=decision, envelope=envelope, receipt=receipt)


def _hash_envelope(envelope: ActionEnvelope) -> str:
    import hashlib
    import json

    canonical = json.dumps(envelope.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
