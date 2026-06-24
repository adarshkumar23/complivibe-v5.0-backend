import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from app.models.organization_internal_signing_key import OrganizationInternalSigningKey


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _legacy_signature(manifest_json: dict) -> tuple[str, str]:
    checksum = hashlib.sha256(_canonical_json(manifest_json).encode("utf-8")).hexdigest()
    secret = get_settings().SECRET_KEY.encode("utf-8")
    signature = hmac.new(secret, checksum.encode("utf-8"), hashlib.sha256).hexdigest()
    return checksum, signature


def test_phase410_manifest_generation_autocreates_signing_key_and_stores_key_id(client, db_session):
    owner = _register(client, "p410-owner1@example.com", "Pass1234!@", "P410 Org1")
    org = _org_id(client, owner)

    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    assert generated.status_code == 201
    payload = generated.json()
    assert payload["key_id"] is not None

    keys = (
        db_session.query(OrganizationInternalSigningKey)
        .filter(OrganizationInternalSigningKey.organization_id == uuid.UUID(org))
        .all()
    )
    assert len(keys) == 1
    assert keys[0].status == "active"
    assert keys[0].purpose == "governance_evidence_manifest"
    manifest = (
        db_session.query(OrganizationGovernanceEvidenceManifest)
        .filter(OrganizationGovernanceEvidenceManifest.organization_id == uuid.UUID(org))
        .one()
    )
    assert manifest.key_id == keys[0].key_id


def test_phase410_manifest_verification_with_key_id_works(client):
    owner = _register(client, "p410-owner2@example.com", "Pass1234!@", "P410 Org2")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    key_id = generated.json()["key_id"]

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200
    payload = verify.json()
    assert payload["valid_hash"] is True
    assert payload["valid_signature"] is True
    assert payload["trusted"] is True
    assert payload["legacy_verification"] is False
    assert payload["key_id"] == key_id
    assert payload["key_status"] == "active"


def test_phase410_legacy_manifest_without_key_id_still_verifies(client, db_session):
    owner = _register(client, "p410-owner3@example.com", "Pass1234!@", "P410 Org3")
    org = _org_id(client, owner)
    me = client.get("/api/v1/auth/me", headers=_headers(owner, org))
    user_id = uuid.UUID(me.json()["id"])

    manifest_json = {
        "manifest_type": "governance_settings_evidence",
        "organization_id": org,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by_user_id": str(user_id),
        "generation_options": {"include_history": False},
        "current_settings": {"batch_cancellation_requires_approval": False},
        "history_entries": [],
        "timeline_entries": [],
        "relevant_audit_action_names": [],
        "caveat": "legacy",
    }
    checksum, signature = _legacy_signature(manifest_json)
    row = OrganizationGovernanceEvidenceManifest(
        organization_id=uuid.UUID(org),
        manifest_type="governance_settings_evidence",
        status="active",
        manifest_json=manifest_json,
        content_sha256=checksum,
        signature_algorithm="HMAC-SHA256",
        internal_signature=signature,
        key_id=None,
        generated_by_user_id=user_id,
        generated_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{row.id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200
    payload = verify.json()
    assert payload["legacy_verification"] is True
    assert payload["valid_hash"] is True
    assert payload["valid_signature"] is True
    assert payload["trusted"] is True
    assert payload["key_id"] is None
    assert payload["key_status"] is None


def test_phase410_rotate_deprecates_old_key_and_creates_new_active_key(client, db_session):
    owner = _register(client, "p410-owner4@example.com", "Pass1234!@", "P410 Org4")
    org = _org_id(client, owner)
    first = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    old_key_id = first.json()["key_id"]

    rotated = client.post(
        "/api/v1/organizations/me/governance-settings/signing-keys/rotate",
        headers=_headers(owner, org),
        json={"reason": "Scheduled rotation"},
    )
    assert rotated.status_code == 200
    new_key_id = rotated.json()["key"]["key_id"]
    assert new_key_id != old_key_id
    assert rotated.json()["key"]["status"] == "active"

    keys = (
        db_session.query(OrganizationInternalSigningKey)
        .filter(OrganizationInternalSigningKey.organization_id == uuid.UUID(org))
        .all()
    )
    by_key = {row.key_id: row for row in keys}
    assert by_key[old_key_id].status == "deprecated"
    assert by_key[new_key_id].status == "active"


def test_phase410_new_manifest_after_rotation_uses_new_key_and_old_manifest_verifies(client):
    owner = _register(client, "p410-owner5@example.com", "Pass1234!@", "P410 Org5")
    org = _org_id(client, owner)
    first = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    first_manifest_id = first.json()["manifest_id"]
    old_key_id = first.json()["key_id"]

    rotate = client.post(
        "/api/v1/organizations/me/governance-settings/signing-keys/rotate",
        headers=_headers(owner, org),
        json={"reason": "Rotate key"},
    )
    assert rotate.status_code == 200
    new_key_id = rotate.json()["key"]["key_id"]

    second = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    assert second.status_code == 201
    assert second.json()["key_id"] == new_key_id

    first_verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{first_manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert first_verify.status_code == 200
    assert first_verify.json()["key_id"] == old_key_id
    assert first_verify.json()["key_status"] == "deprecated"
    assert first_verify.json()["valid_signature"] is True
    assert first_verify.json()["trusted"] is True


def test_phase410_revoked_key_manifest_verifies_but_trusted_false(client):
    owner = _register(client, "p410-owner6@example.com", "Pass1234!@", "P410 Org6")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    key_id = generated.json()["key_id"]

    revoked = client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke",
        headers=_headers(owner, org),
        json={"revocation_reason": "Key compromise drill"},
    )
    assert revoked.status_code == 200

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200
    assert verify.json()["valid_signature"] is True
    assert verify.json()["key_status"] == "revoked"
    assert verify.json()["trusted"] is False


def test_phase410_signing_key_list_never_exposes_secrets(client):
    owner = _register(client, "p410-owner7@example.com", "Pass1234!@", "P410 Org7")
    org = _org_id(client, owner)
    client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )

    listed = client.get(
        "/api/v1/organizations/me/governance-settings/signing-keys",
        headers=_headers(owner, org),
    )
    assert listed.status_code == 200
    payload = listed.json()
    assert payload["keys"]
    key_payload = payload["keys"][0]
    assert "secret" not in key_payload
    assert "key_material" not in key_payload
    assert "internal_key" not in key_payload
    assert payload["caveat"].startswith("These signing keys are internal CompliVibe integrity keys")


def test_phase410_deprecate_requires_reason_and_revoke_requires_reason(client):
    owner = _register(client, "p410-owner8@example.com", "Pass1234!@", "P410 Org8")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    key_id = generated.json()["key_id"]

    missing_deprecate = client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/deprecate",
        headers=_headers(owner, org),
        json={},
    )
    assert missing_deprecate.status_code == 422

    missing_revoke = client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke",
        headers=_headers(owner, org),
        json={},
    )
    assert missing_revoke.status_code == 422


def test_phase410_signing_key_summary_returns_counts(client):
    owner = _register(client, "p410-owner9@example.com", "Pass1234!@", "P410 Org9")
    org = _org_id(client, owner)
    legacy_owner = _register(client, "p410-owner9b@example.com", "Pass1234!@", "P410 Org9b")
    _ = _org_id(client, legacy_owner)  # ensure second org doesn't interfere

    first = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    first_key_id = first.json()["key_id"]
    client.post(
        "/api/v1/organizations/me/governance-settings/signing-keys/rotate",
        headers=_headers(owner, org),
        json={"reason": "Rotate"},
    )
    second = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    second_key_id = second.json()["key_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{first_key_id}/revoke",
        headers=_headers(owner, org),
        json={"revocation_reason": "Retire old key"},
    )

    summary = client.get(
        "/api/v1/organizations/me/governance-settings/signing-keys/summary",
        headers=_headers(owner, org),
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["active_keys"] == 1
    assert payload["deprecated_keys"] == 0
    assert payload["revoked_keys"] == 1
    assert payload["manifests_by_key_id"][second_key_id] >= 1
    assert payload["legacy_manifests_without_key_id"] == 0
    assert payload["caveat"].startswith("These signing keys are internal CompliVibe integrity keys")


def test_phase410_tenant_isolation_and_audit_logs(client, db_session):
    owner1 = _register(client, "p410-owner10@example.com", "Pass1234!@", "P410 Org10")
    owner2 = _register(client, "p410-owner11@example.com", "Pass1234!@", "P410 Org11")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner1, org1),
        json={},
    )
    key_id = generated.json()["key_id"]

    forbidden = client.get(
        "/api/v1/organizations/me/governance-settings/signing-keys",
        headers=_headers(owner2, org1),
    )
    assert forbidden.status_code == 403

    client.post(
        "/api/v1/organizations/me/governance-settings/signing-keys/rotate",
        headers=_headers(owner1, org1),
        json={"reason": "Ops rotation"},
    )
    client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke",
        headers=_headers(owner1, org1),
        json={"revocation_reason": "Retired"},
    )

    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org1))
        .all()
    ]
    assert "organization_internal_signing_key.created" in actions
    assert "organization_internal_signing_key.rotated" in actions
    assert "organization_internal_signing_key.revoked" in actions
    assert "organization_governance_evidence_manifest.generated" in actions
