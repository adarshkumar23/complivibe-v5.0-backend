import uuid

from app.models.audit_log import AuditLog
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from app.models.organization_governance_manifest_verification_event import OrganizationGovernanceManifestVerificationEvent
from app.models.organization_internal_signing_key import OrganizationInternalSigningKey
from tests.helpers.auth_org import bootstrap_org_user, org_headers
from tests.helpers.signed_export_pages import (
    generate_signed_verification_export_page,
    remove_export_signature_field,
    replace_export_key_id,
    tamper_export_page_event,
    tamper_export_page_filters,
)


VERIFY_PAGE_ENDPOINT = (
    "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export/verify-page"
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


def _verify_page(client, token: str, org_id: str, exported_page_json: dict):
    return client.post(
        VERIFY_PAGE_ENDPOINT,
        headers=org_headers(token, org_id),
        json={"exported_page_json": exported_page_json},
    )


def test_phase414_valid_exported_page_verifies_successfully(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner1", organization_name="P414 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    response = _verify_page(client, owner, org, exported)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_signature"] is True
    assert body["valid_signed_payload_hash"] is True
    assert body["valid_canonical_page_hash"] is True
    assert body["trusted"] is True
    assert body["signature_scope"] == "verification_event_export_page"
    assert body["signature_algorithm"] == "HMAC-SHA256"


def test_phase414_tampered_event_fails_page_hash_and_signature(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner2", organization_name="P414 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    tampered = tamper_export_page_event(exported)

    response = _verify_page(client, owner, org, tampered)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_canonical_page_hash"] is False
    assert body["valid_signature"] is False
    assert body["trusted"] is False


def test_phase414_tampered_filters_or_page_metadata_fails_signed_payload_or_signature(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner3", organization_name="P414 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    tampered = tamper_export_page_filters(exported)

    response = _verify_page(client, owner, org, tampered)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_signed_payload_hash"] is False
    assert body["valid_signature"] is False
    assert body["trusted"] is False


def test_phase414_missing_signature_fields_rejected(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner4", organization_name="P414 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    missing = remove_export_signature_field(exported, "internal_signature")

    response = _verify_page(client, owner, org, missing)
    assert response.status_code == 400
    assert response.json()["detail"] == "export_integrity.internal_signature is required"


def test_phase414_unknown_key_id_returns_untrusted_and_invalid_signature(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner5", organization_name="P414 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    unknown = replace_export_key_id(exported, "org-unknown-governance-v999")

    response = _verify_page(client, owner, org, unknown)

    assert response.status_code == 200
    body = response.json()
    assert body["key_status"] == "missing"
    assert body["valid_signature"] is False
    assert body["trusted"] is False


def test_phase414_revoked_key_returns_untrusted_even_if_signature_valid(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner6", organization_name="P414 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    key_id = exported["export_integrity"]["key_id"]

    export_key = (
        db_session.query(OrganizationInternalSigningKey)
        .filter(
            OrganizationInternalSigningKey.organization_id == uuid.UUID(org),
            OrganizationInternalSigningKey.purpose == "verification_event_export",
            OrganizationInternalSigningKey.key_id == key_id,
        )
        .one()
    )
    export_key.status = "revoked"
    export_key.revocation_reason = "phase414 revoke"
    db_session.commit()

    response = _verify_page(client, owner, org, exported)

    assert response.status_code == 200
    body = response.json()
    assert body["key_status"] == "revoked"
    assert body["valid_signature"] is True
    assert body["valid_signed_payload_hash"] is True
    assert body["valid_canonical_page_hash"] is True
    assert body["trusted"] is False


def test_phase414_tenant_mismatch_rejected(client):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner7", organization_name="P414 Org7")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner8", organization_name="P414 Org8")
    owner1 = owner1_bootstrap["access_token"]
    owner2 = owner2_bootstrap["access_token"]
    org1 = owner1_bootstrap["organization_id"]
    org2 = owner2_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner1, org1)
    _verify_manifest(client, owner1, org1, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner1, org1), {"limit": 100})
    response = _verify_page(client, owner2, org2, exported)

    assert response.status_code in (403, 404)


def test_phase414_verify_page_does_not_persist_exported_payload(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner9", organization_name="P414 Org9")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    manifest = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, manifest["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    before_count = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org),
            AuditLog.action == "organization_governance_verification_events.export_page_signature_verified",
        )
        .count()
    )
    before_total_count = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org))
        .count()
    )

    response = _verify_page(client, owner, org, exported)
    assert response.status_code == 200

    after_rows = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org),
            AuditLog.action == "organization_governance_verification_events.export_page_signature_verified",
        )
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    after_total_count = (
        db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org))
        .count()
    )
    assert len(after_rows) == before_count + 1
    assert after_total_count == before_total_count + 1
    verify_log = after_rows[0]
    assert "exported_page_json" not in verify_log.metadata_json
    assert "events" not in verify_log.after_json
    assert "manifest_metadata" not in verify_log.after_json
    assert "chain_context" not in verify_log.after_json


def test_phase414_verify_page_does_not_mutate_manifests_or_verification_events(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner10", organization_name="P414 Org10")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    _verify_manifest(client, owner, org, manifest_id)

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})

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

    response = _verify_page(client, owner, org, exported)
    assert response.status_code == 200

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


def test_phase414_verify_page_writes_audit_log(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p414-owner11", organization_name="P414 Org11")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, generated["manifest_id"])

    exported = generate_signed_verification_export_page(client, org_headers(owner, org), {"limit": 100})
    response = _verify_page(client, owner, org, exported)
    assert response.status_code == 200

    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org))
        .all()
    ]
    assert "organization_governance_verification_events.export_page_signature_verified" in actions
