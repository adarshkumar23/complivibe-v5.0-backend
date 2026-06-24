import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.models.audit_log import AuditLog
from app.models.organization_governance_evidence_manifest import OrganizationGovernanceEvidenceManifest
from app.models.organization_governance_manifest_verification_event import OrganizationGovernanceManifestVerificationEvent
from tests.helpers.auth_org import bootstrap_org_user, org_headers
from tests.helpers.signed_export_pages import generate_signed_verification_export_page


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _legacy_signature(manifest_json: dict) -> tuple[str, str]:
    checksum = hashlib.sha256(_canonical_json(manifest_json).encode("utf-8")).hexdigest()
    secret = get_settings().SECRET_KEY.encode("utf-8")
    signature = hmac.new(secret, checksum.encode("utf-8"), hashlib.sha256).hexdigest()
    return checksum, signature


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


def test_phase412_export_returns_first_page_with_deterministic_ordering(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner1", organization_name="P412 Org1")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    _verify_manifest(client, owner, org, manifest_id)
    _verify_manifest(client, owner, org, manifest_id)
    _verify_manifest(client, owner, org, manifest_id)

    payload = generate_signed_verification_export_page(
        client,
        org_headers(owner, org),
        {"direction": "asc", "limit": 2},
    )
    assert payload["export_type"] == "verification_events_json"
    assert payload["page"]["item_count"] == 2
    events = payload["events"]
    assert len(events) == 2
    ordered = sorted(events, key=lambda item: (item["verified_at"], item["id"]))
    assert events == ordered


def test_phase412_export_returns_next_cursor_and_fetches_next_page_without_duplicates(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner2", organization_name="P412 Org2")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    for _ in range(5):
        _verify_manifest(client, owner, org, manifest_id)

    first = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 2})
    assert first["page"]["has_more"] is True
    assert first["page"]["next_cursor"] is not None

    second = generate_signed_verification_export_page(
        client,
        org_headers(owner, org),
        {"direction": "asc", "limit": 2, "cursor": first["page"]["next_cursor"]},
    )
    first_ids = {item["id"] for item in first["events"]}
    second_ids = {item["id"] for item in second["events"]}
    assert first_ids.isdisjoint(second_ids)


def test_phase412_cursor_rejects_filter_mismatch(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner3", organization_name="P412 Org3")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    for _ in range(3):
        _verify_manifest(client, owner, org, manifest_id)

    first = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 2})
    mismatch = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export",
        headers=org_headers(owner, org),
        json={
            "direction": "asc",
            "limit": 2,
            "trusted": True,
            "cursor": first["page"]["next_cursor"],
        },
    )
    assert mismatch.status_code == 400
    assert "Cursor does not match current export filters" in mismatch.json()["detail"]


def test_phase412_export_limit_and_direction_validation(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner4", organization_name="P412 Org4")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    over_limit = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export",
        headers=org_headers(owner, org),
        json={"limit": 501},
    )
    assert over_limit.status_code == 422

    bad_direction = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests/verification-events/export",
        headers=org_headers(owner, org),
        json={"direction": "sideways"},
    )
    assert bad_direction.status_code == 422


def test_phase412_manifest_id_trusted_and_key_id_filters_work(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner5", organization_name="P412 Org5")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]

    m1 = _generate_manifest(client, owner, org)
    m2 = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, m1["manifest_id"])
    _verify_manifest(client, owner, org, m2["manifest_id"])

    key_id = m1["key_id"]
    revoke = client.post(
        f"/api/v1/organizations/me/governance-settings/signing-keys/{key_id}/revoke",
        headers=org_headers(owner, org),
        json={"revocation_reason": "revoke"},
    )
    assert revoke.status_code == 200
    _verify_manifest(client, owner, org, m1["manifest_id"])

    by_manifest = generate_signed_verification_export_page(
        client,
        org_headers(owner, org),
        {"manifest_id": m1["manifest_id"], "limit": 50},
    )
    assert by_manifest["events"]
    assert {item["manifest_id"] for item in by_manifest["events"]} == {m1["manifest_id"]}

    trusted_only = generate_signed_verification_export_page(client, org_headers(owner, org), {"trusted": True, "limit": 50})
    assert trusted_only["events"]
    assert all(item["trusted"] is True for item in trusted_only["events"])

    by_key = generate_signed_verification_export_page(client, org_headers(owner, org), {"key_id": key_id, "limit": 50})
    assert by_key["events"]
    assert all(item["key_id"] == key_id for item in by_key["events"])


def test_phase412_legacy_verification_and_date_range_filters_work(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner6", organization_name="P412 Org6")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    user_id = uuid.UUID(owner_bootstrap["user_id"])

    regular = _generate_manifest(client, owner, org)
    _verify_manifest(client, owner, org, regular["manifest_id"])
    regular_event = (
        db_session.query(OrganizationGovernanceManifestVerificationEvent)
        .filter(OrganizationGovernanceManifestVerificationEvent.organization_id == uuid.UUID(org))
        .order_by(OrganizationGovernanceManifestVerificationEvent.verified_at.desc())
        .first()
    )
    assert regular_event is not None
    regular_event.verified_at = datetime.now(timezone.utc) - timedelta(days=2)
    regular_event.created_at = regular_event.verified_at
    db_session.commit()

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
    _verify_manifest(client, owner, org, str(legacy_row.id))

    legacy_only = generate_signed_verification_export_page(
        client,
        org_headers(owner, org),
        {"legacy_verification": True, "limit": 50},
    )
    assert legacy_only["events"]
    assert all(item["legacy_verification"] is True for item in legacy_only["events"])

    window_start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    window_end = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    recent_only = generate_signed_verification_export_page(
        client,
        org_headers(owner, org),
        {"from_verified_at": window_start, "to_verified_at": window_end, "limit": 50},
    )
    assert recent_only["events"]
    assert all(item["verified_at"] >= window_start for item in recent_only["events"])


def test_phase412_export_does_not_mutate_manifests_or_verification_events(client, db_session):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner7", organization_name="P412 Org7")
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
        (
            row.id,
            row.manifest_id,
            row.verified_at,
            row.valid_hash,
            row.valid_signature,
            row.trusted,
        )
        for row in events_before
    ]

    generate_signed_verification_export_page(
        client,
        org_headers(owner, org),
        {"limit": 50, "include_manifest_metadata": True, "include_chain_context": True},
    )

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
        (
            row.id,
            row.manifest_id,
            row.verified_at,
            row.valid_hash,
            row.valid_signature,
            row.trusted,
        )
        for row in events_after
    ] == event_snapshot


def test_phase412_canonical_page_sha256_is_stable(client):
    owner_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner8", organization_name="P412 Org8")
    owner = owner_bootstrap["access_token"]
    org = owner_bootstrap["organization_id"]
    generated = _generate_manifest(client, owner, org)
    manifest_id = generated["manifest_id"]
    _verify_manifest(client, owner, org, manifest_id)
    _verify_manifest(client, owner, org, manifest_id)

    first = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 100})
    second = generate_signed_verification_export_page(client, org_headers(owner, org), {"direction": "asc", "limit": 100})
    assert first["export_integrity"]["canonical_page_sha256"] == second["export_integrity"]["canonical_page_sha256"]


def test_phase412_export_writes_audit_log_and_enforces_tenant_isolation(client, db_session):
    owner1_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner9", organization_name="P412 Org9")
    owner2_bootstrap = bootstrap_org_user(client, email_prefix="p412-owner10", organization_name="P412 Org10")
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

    generate_signed_verification_export_page(client, org_headers(owner1, org1), {"limit": 10})
    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org1))
        .all()
    ]
    assert "organization_governance_verification_events.exported" in actions
