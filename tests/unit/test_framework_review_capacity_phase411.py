import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from app.models.organization_governance_manifest_verification_event import OrganizationGovernanceManifestVerificationEvent


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


def test_phase411_verify_creates_immutable_verification_event(client, db_session):
    owner = _register(client, "p411-owner1@example.com", "Pass1234!@", "P411 Org1")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200
    payload = verify.json()
    assert payload["verification_event_id"] is not None

    rows = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .all()
    )
    assert len(rows) == 1
    assert rows[0].manifest_id == uuid.UUID(manifest_id)
    assert rows[0].caveat.startswith("Manifest verification is an internal CompliVibe integrity check")


def test_phase411_event_captures_actor_time_result_key_status_trusted_snapshot(client, db_session):
    owner = _register(client, "p411-owner2@example.com", "Pass1234!@", "P411 Org2")
    org = _org_id(client, owner)
    me = client.get("/api/v1/auth/me", headers=_headers(owner, org))
    user_id = uuid.UUID(me.json()["id"])
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

    row = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .one()
    )
    assert row.verified_by_user_id == user_id
    assert row.verified_at is not None
    assert row.valid_hash is True
    assert row.valid_signature is True
    assert row.trusted is True
    assert row.key_id == key_id
    assert row.key_status == "active"
    assert row.legacy_verification is False
    assert row.verification_result_json["trusted"] is True


def test_phase411_verification_does_not_mutate_manifest(client, db_session):
    owner = _register(client, "p411-owner3@example.com", "Pass1234!@", "P411 Org3")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = uuid.UUID(generated.json()["manifest_id"])
    before = db_session.query(OrganizationGovernanceEvidenceManifest).filter(
        OrganizationGovernanceEvidenceManifest.id == manifest_id
    ).one()
    before_state = (
        before.status,
        before.key_id,
        before.content_sha256,
        before.internal_signature,
        before.signature_algorithm,
        before.revoked_at,
        before.revoked_by_user_id,
        before.revocation_reason,
    )

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200

    after = db_session.query(OrganizationGovernanceEvidenceManifest).filter(
        OrganizationGovernanceEvidenceManifest.id == manifest_id
    ).one()
    after_state = (
        after.status,
        after.key_id,
        after.content_sha256,
        after.internal_signature,
        after.signature_algorithm,
        after.revoked_at,
        after.revoked_by_user_id,
        after.revocation_reason,
    )
    assert after_state == before_state


def test_phase411_revoked_key_verification_creates_event_trusted_false(client, db_session):
    owner = _register(client, "p411-owner4@example.com", "Pass1234!@", "P411 Org4")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    key_id = generated.json()["key_id"]
    revoke_key = client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke",
        headers=_headers(owner, org),
        json={"revocation_reason": "Retire key"},
    )
    assert revoke_key.status_code == 200

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200
    assert verify.json()["trusted"] is False

    row = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .order_by(OrganizationGovernanceManifestVerificationEvent.verified_at.desc())
        .first()
    )
    assert row is not None
    assert row.key_status == "revoked"
    assert row.trusted is False


def test_phase411_legacy_verification_creates_event_with_legacy_true(client, db_session):
    owner = _register(client, "p411-owner5@example.com", "Pass1234!@", "P411 Org5")
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
    legacy_row = OrganizationGovernanceEvidenceManifest(
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
    db_session.add(legacy_row)
    db_session.commit()
    db_session.refresh(legacy_row)

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{legacy_row.id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200
    assert verify.json()["legacy_verification"] is True

    event = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .order_by(OrganizationGovernanceManifestVerificationEvent.verified_at.desc())
        .first()
    )
    assert event is not None
    assert event.legacy_verification is True


def test_phase411_list_events_for_manifest_tenant_scoped(client):
    owner1 = _register(client, "p411-owner6@example.com", "Pass1234!@", "P411 Org6")
    owner2 = _register(client, "p411-owner7@example.com", "Pass1234!@", "P411 Org7")
    org1 = _org_id(client, owner1)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner1, org1),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner1, org1),
    )

    forbidden = client.get(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verification-events",
        headers=_headers(owner2, org1),
    )
    assert forbidden.status_code == 403


def test_phase411_list_all_events_tenant_scoped(client):
    owner1 = _register(client, "p411-owner8@example.com", "Pass1234!@", "P411 Org8")
    owner2 = _register(client, "p411-owner9@example.com", "Pass1234!@", "P411 Org9")
    org1 = _org_id(client, owner1)
    org2 = _org_id(client, owner2)

    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner1, org1),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner1, org1),
    )

    forbidden = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events",
        headers=_headers(owner2, org1),
    )
    assert forbidden.status_code == 403

    own = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events",
        headers=_headers(owner2, org2),
    )
    assert own.status_code == 200
    assert own.json()["events"] == []


def test_phase411_chain_of_custody_includes_generation_and_verification_events(client):
    owner = _register(client, "p411-owner10@example.com", "Pass1234!@", "P411 Org10")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )

    chain = client.get(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/chain-of-custody",
        headers=_headers(owner, org),
    )
    assert chain.status_code == 200
    payload = chain.json()
    event_types = {item["event_type"] for item in payload["entries"]}
    assert "manifest_generated" in event_types
    assert "manifest_verified" in event_types
    assert payload["caveat"].startswith("Manifest verification is an internal CompliVibe integrity check")


def test_phase411_verification_summary_returns_counts(client):
    owner = _register(client, "p411-owner11@example.com", "Pass1234!@", "P411 Org11")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    key_id = generated.json()["key_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke",
        headers=_headers(owner, org),
        json={"revocation_reason": "Test revoked"},
    )
    client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )

    summary = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-summary",
        headers=_headers(owner, org),
    )
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_verifications"] == 2
    assert payload["trusted_verifications"] == 1
    assert payload["untrusted_verifications"] == 1
    assert payload["revoked_key_verifications"] == 1
    assert payload["latest_verification_at"] is not None


def test_phase411_audit_log_written_on_verify(client, db_session):
    owner = _register(client, "p411-owner12@example.com", "Pass1234!@", "P411 Org12")
    org = _org_id(client, owner)
    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]
    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=_headers(owner, org),
    )
    assert verify.status_code == 200

    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org))
        .all()
    ]
    assert "organization_governance_evidence_manifest.verified" in actions
