import uuid

from app.models.audit_log import AuditLog
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from tests.helpers.auth_org import bootstrap_org_user, org_headers


def _set_org_default(client, token: str, org_id: str, enabled: bool, reason: str) -> None:
    response = client.patch(
        "/api/v1/organizations/me/governance-settings",
        headers=org_headers(token, org_id),
        json={
            "batch_cancellation_requires_approval": enabled,
            "batch_cancellation_policy_reason": reason,
        },
    )
    assert response.status_code == 200


def test_phase49_generate_manifest_works_and_stores_hash_signature(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner1", organization_name="P49 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    _set_org_default(client, owner, org, True, "Enable default")

    response = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["manifest_type"] == "governance_settings_evidence"
    assert len(payload["content_sha256"]) == 64
    assert payload["signature_algorithm"] == "HMAC-SHA256"
    assert len(payload["internal_signature"]) == 64
    assert payload["caveat"].startswith("This manifest uses an internal integrity signature")

    rows = (
        db_session.query(OrganizationGovernanceEvidenceManifest)
        .filter(OrganizationGovernanceEvidenceManifest.organization_id == uuid.UUID(org))
        .all()
    )
    assert len(rows) == 1
    assert rows[0].content_sha256 == payload["content_sha256"]
    assert rows[0].internal_signature == payload["internal_signature"]


def test_phase49_verify_manifest_valid_hash_and_signature(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner2", organization_name="P49 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    manifest_id = generated.json()["manifest_id"]

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=org_headers(owner, org),
    )
    assert verify.status_code == 200
    payload = verify.json()
    assert payload["valid_hash"] is True
    assert payload["valid_signature"] is True
    assert payload["status"] == "active"


def test_phase49_list_manifests_tenant_scoped(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner3", organization_name="P49 Org3")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner4", organization_name="P49 Org4")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]

    created = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner1, org1),
        json={},
    )
    assert created.status_code == 201

    forbidden = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner2, org1),
    )
    assert forbidden.status_code == 403

    own_list = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner1, org1),
    )
    assert own_list.status_code == 200
    assert len(own_list.json()["manifests"]) == 1
    assert own_list.json()["caveat"].startswith("This manifest uses an internal integrity signature")

    other_list = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner2, org2),
    )
    assert other_list.status_code == 200
    assert other_list.json()["manifests"] == []


def test_phase49_manifest_detail_tenant_scoped(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner5", organization_name="P49 Org5")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner6", organization_name="P49 Org6")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]

    created = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner1, org1),
        json={},
    )
    manifest_id = created.json()["manifest_id"]

    forbidden = client.get(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}",
        headers=org_headers(owner2, org1),
    )
    assert forbidden.status_code == 403


def test_phase49_revoke_requires_reason(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner7", organization_name="P49 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    created = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    manifest_id = created.json()["manifest_id"]

    missing = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke",
        headers=org_headers(owner, org),
        json={},
    )
    assert missing.status_code == 422


def test_phase49_revoked_manifest_still_verifies_and_status_revoked(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner8", organization_name="P49 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    created = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    manifest_id = created.json()["manifest_id"]

    revoked = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke",
        headers=org_headers(owner, org),
        json={"revocation_reason": "Superseded by a newer manifest"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["manifest"]["status"] == "revoked"

    verify = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=org_headers(owner, org),
    )
    assert verify.status_code == 200
    assert verify.json()["valid_hash"] is True
    assert verify.json()["valid_signature"] is True
    assert verify.json()["status"] == "revoked"


def test_phase49_revoke_does_not_delete_or_mutate_manifest_json(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner9", organization_name="P49 Org9")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    created = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    manifest_id = uuid.UUID(created.json()["manifest_id"])
    before = db_session.query(OrganizationGovernanceEvidenceManifest).filter(
        OrganizationGovernanceEvidenceManifest.id == manifest_id
    ).one()
    manifest_json_before = before.manifest_json
    hash_before = before.content_sha256
    signature_before = before.internal_signature

    revoked = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke",
        headers=org_headers(owner, org),
        json={"revocation_reason": "Deprecated"},
    )
    assert revoked.status_code == 200

    after = db_session.query(OrganizationGovernanceEvidenceManifest).filter(
        OrganizationGovernanceEvidenceManifest.id == manifest_id
    ).one()
    assert after.status == "revoked"
    assert after.manifest_json == manifest_json_before
    assert after.content_sha256 == hash_before
    assert after.internal_signature == signature_before


def test_phase49_from_to_version_filtering_works(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner10", organization_name="P49 Org10")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    _set_org_default(client, owner, org, True, "Version one")
    _set_org_default(client, owner, org, False, "Version two")

    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={"include_history": True, "from_version": 2, "to_version": 2},
    )
    assert generated.status_code == 201
    manifest_id = generated.json()["manifest_id"]
    detail = client.get(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}",
        headers=org_headers(owner, org),
    )
    assert detail.status_code == 200
    versions = [entry["version"] for entry in detail.json()["manifest_json"]["history_entries"]]
    assert versions == [2]


def test_phase49_audit_logs_written_for_generate_and_revoke(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner11", organization_name="P49 Org11")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    generated = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    assert generated.status_code == 201
    manifest_id = generated.json()["manifest_id"]

    revoked = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke",
        headers=org_headers(owner, org),
        json={"revocation_reason": "Superseded"},
    )
    assert revoked.status_code == 200

    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org))
        .all()
    ]
    assert "organization_governance_evidence_manifest.generated" in actions
    assert "organization_governance_evidence_manifest.revoked" in actions


def test_phase49_list_filter_by_status(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p49-owner12", organization_name="P49 Org12")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    created = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        json={},
    )
    manifest_id = created.json()["manifest_id"]
    client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/revoke",
        headers=org_headers(owner, org),
        json={"revocation_reason": "Superseded"},
    )

    active = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        params={"status": "active"},
    )
    assert active.status_code == 200
    assert active.json()["manifests"] == []

    revoked = client.get(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(owner, org),
        params={"status": "revoked"},
    )
    assert revoked.status_code == 200
    assert len(revoked.json()["manifests"]) == 1
    assert revoked.json()["manifests"][0]["status"] == "revoked"
