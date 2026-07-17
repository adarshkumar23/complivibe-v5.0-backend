"""Additional coverage for the content-provenance router
(/api/v1/content-provenance). Complements test_c2pa_content_provenance_t4_12.py.

The existing t4_12 suite proves manifest structural/signature validation, history,
drift, cross-org 404, audit logging, and the auditor 403 path. This file adds the
genuinely-uncovered surface:
  * the content_sha256 hard-binding hash comparison (match / mismatch / absent),
    including the content_hash_verified audit flag,
  * a non-owner role that HOLDS content_provenance:manage (compliance_manager) is
    authorized, while a role that lacks it (readonly) is forbidden,
  * schema-level rejection of a too-short content_sha256,
  * GET of a syntactically-valid but nonexistent record id -> 404.
"""

from __future__ import annotations

import base64
import copy
import json
import uuid

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.models.audit_log import AuditLog
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

VERIFY_URL = "/api/v1/content-provenance/verify"

# A real 64-char hex SHA-256 digest of the "actual asset bytes".
ASSET_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


def _sign(manifest: dict) -> dict:
    private_key = Ed25519PrivateKey.generate()
    signed = copy.deepcopy(manifest)
    canonical = json.dumps(signed, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    signature = private_key.sign(canonical)
    public_key = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    signed["signature_info"] = {
        "algorithm": "ed25519",
        "signature": base64.b64encode(signature).decode("ascii"),
        "public_key": base64.b64encode(public_key).decode("ascii"),
    }
    return signed


def _manifest_with_hash(hash_value: str | None) -> dict:
    assertions = [{"label": "c2pa.actions", "data": {"actions": [{"action": "c2pa.created"}]}}]
    if hash_value is not None:
        assertions.append({"label": "c2pa.hash.data", "data": {"hash": hash_value}})
    return _sign(
        {
            "claim_generator": "AcmeCam/1.0",
            "spec_version": "c2pa-1.2",
            "assertions": assertions,
        }
    )


def _content_hash_verified_flag(db_session, org_id: str, record_id: str) -> bool:
    row = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org_id),
            AuditLog.action == "content_provenance.manifest_verified",
            AuditLog.entity_id == uuid.UUID(record_id),
        )
        .one()
    )
    return row.metadata_json["content_hash_verified"]


def test_hard_binding_hash_match_verifies_valid(client, db_session):
    """Real cryptographic tamper detection: asset digest matches the manifest's
    c2pa.hash.* hard binding -> valid, and the audit trail records that a genuine
    hash comparison (not just a shape check) was performed."""
    org = bootstrap_org_user(client, email_prefix="cp-hash-ok")
    manifest = _manifest_with_hash(ASSET_SHA256)

    r = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-hash-ok", "manifest": manifest, "content_sha256": ASSET_SHA256},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verification_status"] == "valid"
    assert body["invalid_reason"] is None
    assert body["assertion_count"] == 2
    assert _content_hash_verified_flag(db_session, org["organization_id"], body["id"]) is True


def test_hard_binding_hash_mismatch_is_tampered(client, db_session):
    """Asset digest does NOT match the manifest's declared hard-binding hash -> the
    bytes were tampered even though the signature over the claim is well-formed."""
    org = bootstrap_org_user(client, email_prefix="cp-hash-bad")
    # Manifest commits to ASSET_SHA256, but the real asset digest is different.
    manifest = _manifest_with_hash(ASSET_SHA256)
    different_digest = "a" * 64

    r = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-hash-bad", "manifest": manifest, "content_sha256": different_digest},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verification_status"] == "invalid"
    assert body["invalid_reason"] == "tampered_signature"
    # No hard-binding comparison "passed": the manifest had a hash but it did not
    # match; content_hash_verified reflects that a digest+binding were both present.
    assert _content_hash_verified_flag(db_session, org["organization_id"], body["id"]) is True


def test_content_sha256_without_hard_binding_stays_valid_but_unverified(client, db_session):
    """A digest is supplied but the manifest carries no c2pa.hash.* assertion, so no
    real comparison is possible: the manifest still validates structurally, but the
    audit flag records that no genuine hash verification occurred."""
    org = bootstrap_org_user(client, email_prefix="cp-hash-none")
    manifest = _manifest_with_hash(None)

    r = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-hash-none", "manifest": manifest, "content_sha256": ASSET_SHA256},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verification_status"] == "valid"
    assert body["assertion_count"] == 1
    assert _content_hash_verified_flag(db_session, org["organization_id"], body["id"]) is False


def test_content_sha256_too_short_rejected_by_schema(client, db_session):
    """content_sha256 has a 32-char minimum; a shorter value is a request-shape
    error (422) before any provenance logic runs."""
    org = bootstrap_org_user(client, email_prefix="cp-hash-short")
    r = client.post(
        VERIFY_URL,
        headers=org["org_headers"],
        json={"content_identifier": "asset-short", "manifest": _manifest_with_hash(None), "content_sha256": "abc123"},
    )
    assert r.status_code == 422, r.text


def test_compliance_manager_authorized_readonly_forbidden(client, db_session):
    """content_provenance:manage is granted to compliance_manager (a non-owner role)
    but withheld from readonly."""
    org = bootstrap_org_user(client, email_prefix="cp-perm")

    manager = add_org_member(db_session, client, org["organization_id"], "cp-manager@example.com", role_name="compliance_manager")
    ok = client.post(
        VERIFY_URL,
        headers=manager,
        json={"content_identifier": "asset-mgr", "manifest": _manifest_with_hash(None)},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["verification_status"] == "valid"

    reader = add_org_member(db_session, client, org["organization_id"], "cp-reader@example.com", role_name="readonly")
    denied = client.post(
        VERIFY_URL,
        headers=reader,
        json={"content_identifier": "asset-ro", "manifest": _manifest_with_hash(None)},
    )
    assert denied.status_code == 403, denied.text


def test_get_nonexistent_record_returns_404(client, db_session):
    """A well-formed but unknown record id in the caller's own org -> 404 (distinct
    from the cross-org 404 already covered)."""
    org = bootstrap_org_user(client, email_prefix="cp-missing")
    r = client.get(f"/api/v1/content-provenance/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text
