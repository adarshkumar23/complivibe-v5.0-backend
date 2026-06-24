import uuid

from app.models.audit_log import AuditLog
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from app.models.organization_governance_manifest_verification_event import OrganizationGovernanceManifestVerificationEvent
from app.models.organization_internal_signing_key import OrganizationInternalSigningKey
from tests.helpers.auth_org import bootstrap_org_user, org_headers
from tests.helpers.signed_export_pages import (
    generate_signed_verification_export_page,
    generate_unsigned_verification_export_page,
)


def _generate_manifest(client, token: str, org_id: str) -> dict:
    response = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=org_headers(token, org_id),
        json={},
    )
    assert response.status_code == 201
    return response.json()


def _verify_manifest(client, token: str, org_id: str, manifest_id: str) -> dict:
    response = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=org_headers(token, org_id),
    )
    assert response.status_code == 200
    return response.json()


def test_phase413_export_includes_internal_signature_by_default(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner1", organization_name="P413 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, generated["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    integrity = exported["export_integrity"]
    assert integrity["internal_signature"] is not None
    assert integrity["signed_payload_sha256"] is not None
    assert integrity["signature_scope"] == "verification_event_export_page"
    assert "internal CompliVibe integrity signature" in exported["caveat"]


def test_phase413_export_can_disable_internal_signature(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner2", organization_name="P413 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, generated["manifest_id"])

    exported = generate_unsigned_verification_export_page(client, org_headers(owner, org))
    integrity = exported["export_integrity"]
    assert integrity["internal_signature"] is None
    assert integrity["signature_algorithm"] is None
    assert integrity["key_id"] is None
    assert integrity["key_status"] is None
    assert integrity["signature_scope"] is None
    assert integrity["signed_payload_sha256"] is None


def test_phase413_export_signature_has_key_id_and_algorithm_and_autocreates_export_purpose_key(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner3", organization_name="P413 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, generated["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org))
    integrity = exported["export_integrity"]
    assert integrity["key_id"] is not None
    assert integrity["signature_algorithm"] == "HMAC-SHA256"
    assert integrity["key_status"] == "active"

    keys = (
        db_session.query(OrganizationInternalSigningKey)
        .filter(OrganizationInternalSigningKey.organization_id == uuid.UUID(org))
        .all()
    )
    purposes = {row.purpose for row in keys}
    assert "verification_event_export" in purposes


def test_phase413_governance_evidence_manifest_purpose_is_not_broken(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner4", organization_name="P413 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    _verify_manifest(client, owner, org, manifest_id)
    generate_signed_verification_export_page(client, org_headers(owner, org))

    verify_again = client.post(
        f"/api/v1/organizations/me/governance-settings/evidence-manifests/{manifest_id}/verify",
        headers=org_headers(owner, org),
    )
    assert verify_again.status_code == 200
    assert verify_again.json()["valid_signature"] is True

    keys = (
        db_session.query(OrganizationInternalSigningKey)
        .filter(OrganizationInternalSigningKey.organization_id == uuid.UUID(org))
        .all()
    )
    purposes = {row.purpose for row in keys}
    assert "governance_evidence_manifest" in purposes
    assert "verification_event_export" in purposes


def test_phase413_signed_payload_hash_is_stable_for_same_page(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner5", organization_name="P413 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, generated["manifest_id"])

    first = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 100})
    second = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 100})
    assert first["export_integrity"]["signed_payload_sha256"] == second["export_integrity"]["signed_payload_sha256"]
    assert first["export_integrity"]["internal_signature"] == second["export_integrity"]["internal_signature"]


def test_phase413_signature_changes_when_page_events_change(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner6", organization_name="P413 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    _verify_manifest(client, owner, org, manifest_id)

    first = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 100})
    _verify_manifest(client, owner, org, manifest_id)
    second = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 100})

    assert first["export_integrity"]["signed_payload_sha256"] != second["export_integrity"]["signed_payload_sha256"]
    assert first["export_integrity"]["internal_signature"] != second["export_integrity"]["internal_signature"]


def test_phase413_export_signature_does_not_mutate_manifests_or_events(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner7", organization_name="P413 Org7")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    _verify_manifest(client, owner, org, manifest_id)

    manifest_before = (
        db_session.query(OrganizationGovernanceEvidenceManifest)
        .filter(OrganizationGovernanceEvidenceManifest.id == uuid.UUID(manifest_id))
        .one()
    )
    events_before = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .all()
    )
    manifest_snapshot = (
        manifest_before.status,
        manifest_before.content_sha256,
        manifest_before.internal_signature,
        manifest_before.key_id,
    )
    event_snapshot = [
        (row.id, row.manifest_id, row.verified_at, row.valid_hash, row.valid_signature, row.trusted) for row in events_before
    ]

    generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 50})

    manifest_after = (
        db_session.query(OrganizationGovernanceEvidenceManifest)
        .filter(OrganizationGovernanceEvidenceManifest.id == uuid.UUID(manifest_id))
        .one()
    )
    events_after = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .all()
    )
    assert (
        manifest_after.status,
        manifest_after.content_sha256,
        manifest_after.internal_signature,
        manifest_after.key_id,
    ) == manifest_snapshot
    assert [
        (row.id, row.manifest_id, row.verified_at, row.valid_hash, row.valid_signature, row.trusted) for row in events_after
    ] == event_snapshot


def test_phase413_export_signature_tenant_isolation_and_audit_log(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner8", organization_name="P413 Org8")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p413-owner9", organization_name="P413 Org9")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner1, org1)
    _verify_manifest(client, owner1, org1, generated["manifest_id"])

    forbidden = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export",
        headers=org_headers(owner2, org1),
        json={},
    )
    assert forbidden.status_code == 403

    generate_signed_verification_export_page(client, org_headers(owner1, org1))
    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org1))
        .all()
    ]
    assert "organization_governance_verification_events.exported" in actions
