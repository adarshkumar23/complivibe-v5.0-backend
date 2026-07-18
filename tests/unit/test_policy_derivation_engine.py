"""Unit tests for the agentic policy-derivation feature (patent P3).

Covers the novel derivation engine (Claim 1 provenance), per-tenant Rego
isolation (Claim 3), the first-party Ed25519 receipt primitive + chain
verification (Claim 4 crypto + tamper detection), the envelope/payload trust
boundary, and the patent's own RBI data-localization benchmark
(tests/benchmark/PATENT_TECHNICAL_EFFECT.md) re-derived against the real `opa`
binary.

No DB required; OPA-dependent assertions skip cleanly when `opa` is absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.ai_governance.services.policy_derivation.derivation_engine import (
    ObligationRecord,
    derive_and_compile,
    derive_constraint_spec,
)
from app.ai_governance.services.policy_derivation.envelope import build_envelope
from app.ai_governance.services.policy_derivation.receipt_chain import verify_chain
from app.ai_governance.services.policy_derivation.receipt_crypto import ReceiptSigner, verify_receipt

OPA = shutil.which("opa")
opa_required = pytest.mark.skipif(OPA is None, reason="opa CLI not on PATH")

# 32-byte hex seed for a deterministic demo signing key (customer-side key).
_KEY = "cd" * 32

RBI_OBLIGATION = ObligationRecord(
    id="obl-rbi-2018-dpss",
    text=(
        "All data relating to payment systems operated by payment system operators "
        "shall be stored only in India; this data shall not leave the territory of India "
        "except for the limited purpose of processing a cross-border transaction, and "
        "personal data collected from customers is prohibited from being transferred "
        "outside the territory of India."
    ),
    jurisdiction="India",
    framework="RBI Storage of Payment System Data",
    citation="RBI/2017-18/153",
    control_ids=("CTRL-DATA-RESIDENCY-01",),
)


# --------------------------------------------------------------------------- #
# Claim 1 -- derivation produces a provenance-tagged constraint spec
# --------------------------------------------------------------------------- #
def test_derivation_produces_provenance_tagged_spec():
    spec = derive_constraint_spec([RBI_OBLIGATION])
    assert spec.geographic_scope is not None
    assert spec.geographic_scope.residency_required is True
    assert spec.geographic_scope.allowed_regions == ("India",)
    assert spec.geographic_scope.source_obligation_ids == ("obl-rbi-2018-dpss",)
    assert spec.data_scope is not None
    assert spec.data_scope.cross_border_transfer_allowed is False
    assert "pii" in spec.data_scope.restricted_categories
    assert spec.data_scope.source_obligation_ids == ("obl-rbi-2018-dpss",)
    assert spec.unrecognized_obligation_ids == ()


def test_unrecognized_obligation_is_surfaced_not_dropped():
    junk = ObligationRecord(id="obl-noise", text="This clause contains no derivable constraint.")
    spec = derive_constraint_spec([RBI_OBLIGATION, junk])
    # RBI still derived; the noise obligation is flagged, never silently dropped.
    assert "obl-noise" in spec.unrecognized_obligation_ids
    assert spec.geographic_scope is not None


def test_financial_and_approval_families():
    obl = ObligationRecord(
        id="obl-fin",
        text="A single transfer shall not exceed ₹200000 per transaction and requires prior approval by two approvers.",
    )
    spec = derive_constraint_spec([obl])
    assert spec.financial_limits and spec.financial_limits[0].currency == "INR"
    assert spec.financial_limits[0].max_amount == 200000.0
    assert spec.approval_requirements and spec.approval_requirements[0].min_approvers == 2


# --------------------------------------------------------------------------- #
# Claim 3 -- compiled Rego is scoped to a per-tenant package
# --------------------------------------------------------------------------- #
@opa_required
def test_compiled_rego_is_scoped_to_tenant_package():
    _, rego_text = derive_and_compile([RBI_OBLIGATION], org_id="acme-bank", opa_path=OPA)
    assert "package complivibe.guardrails.org_acme_bank" in rego_text


@opa_required
def test_two_tenants_get_distinct_packages():
    _, rego_a = derive_and_compile([RBI_OBLIGATION], org_id="org-a", opa_path=OPA)
    _, rego_b = derive_and_compile([RBI_OBLIGATION], org_id="org-b", opa_path=OPA)
    assert "org_org_a" in rego_a
    assert "org_org_b" in rego_b
    assert "org_org_a" not in rego_b


# --------------------------------------------------------------------------- #
# Patent benchmark (Workstream M): real opa eval of the RBI scenario
# --------------------------------------------------------------------------- #
def _opa_eval(rego_text: str, input_data: dict, query: str) -> object:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".rego", delete=False) as f:
        f.write(rego_text)
        rego_path = f.name
    try:
        proc = subprocess.run(
            ["opa", "eval", "--format", "json", "--input", "/dev/stdin", "--data", rego_path, query],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert proc.returncode == 0, f"opa eval failed: {proc.stderr}"
        return json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
    finally:
        Path(rego_path).unlink(missing_ok=True)


@opa_required
def test_benchmark_cross_border_to_singapore_denied():
    _, rego = derive_and_compile([RBI_OBLIGATION], org_id="acme-bank", opa_path=OPA)
    result = _opa_eval(
        rego,
        {"action": {"amount": 0, "cross_border": True, "data_categories": ["pii"], "destination_region": "Singapore"}},
        "data.complivibe.guardrails.org_acme_bank.allow",
    )
    assert result is False


@opa_required
def test_benchmark_domestic_india_transfer_allowed():
    _, rego = derive_and_compile([RBI_OBLIGATION], org_id="acme-bank", opa_path=OPA)
    result = _opa_eval(
        rego,
        {"action": {"amount": 0, "cross_border": False, "data_categories": ["pii"], "destination_region": "India"}},
        "data.complivibe.guardrails.org_acme_bank.allow",
    )
    assert result is True


# --------------------------------------------------------------------------- #
# Claim 4 -- Ed25519 receipt signing, key-free verification, tamper detection
# --------------------------------------------------------------------------- #
def test_receipt_signs_and_verifies_key_free():
    signer = ReceiptSigner(_KEY)
    receipt = signer.sign_receipt(
        decision="allow", reasons=["ok"], envelope_hash="abc", previous_receipt_hash=None, timestamp="2026-07-18T00:00:00+00:00"
    )
    # verify_receipt takes ONLY the receipt (carrying a public key); no private key.
    assert verify_receipt(receipt) is True
    assert receipt.public_key_hex == signer.public_key_hex


def test_receipt_tamper_is_detected():
    signer = ReceiptSigner(_KEY)
    receipt = signer.sign_receipt(
        decision="allow", reasons=[], envelope_hash="abc", previous_receipt_hash=None, timestamp="2026-07-18T00:00:00+00:00"
    )
    # Flip the decision after signing -> hash + signature no longer match.
    tampered = type(receipt)(**{**receipt.__dict__, "decision": "deny"})
    assert verify_receipt(tampered) is False


def test_signing_key_never_appears_on_the_receipt():
    signer = ReceiptSigner(_KEY)
    receipt = signer.sign_receipt(
        decision="deny", reasons=["nope"], envelope_hash="h", previous_receipt_hash=None, timestamp="2026-07-18T00:00:00+00:00"
    )
    # The private seed must never leak into any serialized receipt field.
    assert _KEY not in json.dumps(receipt.__dict__)


def test_chain_verifies_and_detects_broken_link():
    signer = ReceiptSigner(_KEY)
    r0 = signer.sign_receipt(decision="allow", reasons=[], envelope_hash="e0", previous_receipt_hash=None, timestamp="2026-07-18T00:00:00+00:00")
    r1 = signer.sign_receipt(decision="deny", reasons=[], envelope_hash="e1", previous_receipt_hash=r0.receipt_hash, timestamp="2026-07-18T00:00:01+00:00")
    good = verify_chain([r0, r1])
    assert good.passed and good.verified_count == 2

    # Break the link: r1 now points at the wrong parent.
    broken_r1 = type(r1)(**{**r1.__dict__, "previous_receipt_hash": "deadbeef"})
    bad = verify_chain([r0, broken_r1])
    assert bad.passed is False and bad.failure_index == 1


# --------------------------------------------------------------------------- #
# Envelope / payload trust boundary
# --------------------------------------------------------------------------- #
def test_envelope_rejects_payload_fields_without_leaking_values():
    with pytest.raises(ValueError) as exc:
        build_envelope(
            {
                "action_id": "a1",
                "ai_system_id": "s1",
                "organization_id": "o1",
                "action_type": "transfer",
                "timestamp": "2026-07-18T00:00:00+00:00",
                "customer_pii": {"ssn": "SECRET-VALUE"},
            }
        )
    msg = str(exc.value)
    assert "customer_pii" in msg
    assert "SECRET-VALUE" not in msg  # value never echoed


def test_envelope_accepts_clean_action():
    env = build_envelope(
        {
            "action_id": "a1",
            "ai_system_id": "s1",
            "organization_id": "o1",
            "action_type": "transfer",
            "amount": 10.0,
            "currency": "INR",
            "timestamp": "2026-07-18T00:00:00+00:00",
        }
    )
    assert env.action_type == "transfer"
