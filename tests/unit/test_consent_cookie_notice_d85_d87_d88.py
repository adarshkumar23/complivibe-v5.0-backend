from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.audit_log import AuditLog
from app.models.consent_record import ConsentRecord
from app.models.cookie_registry import CookieRegistry
from app.models.email_outbox import EmailOutbox
from app.models.google_consent_mode_event import GoogleConsentModeEvent
from app.models.notice_user_acknowledgement import NoticeUserAcknowledgement
from app.privacy.services.consent_service import ConsentService
from tests.helpers.auth_org import bootstrap_org_user


NOTICES_BASE = "/api/v1/privacy/notices"
CONSENT_BASE = "/api/v1/privacy/consent"
COOKIES_BASE = "/api/v1/privacy"
ROPA_BASE = "/api/v1/privacy/ropa"
ASSETS_BASE = "/api/v1/data-observability/assets"
LINEAGE_BASE = "/api/v1/data-observability/lineage"


def _create_notice(client, headers: dict[str, str], **overrides):
    payload = {
        "title": "Privacy Notice",
        "content": "This is our privacy notice.",
        "language": "en",
        "frameworks": ["gdpr"],
    }
    payload.update(overrides)
    response = client.post(NOTICES_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_processing_activity(client, headers: dict[str, str], owner_id: str, **overrides):
    payload = {
        "name": "Consent Activity",
        "description": "Tracks user consent",
        "purpose": "Consent tracking",
        "legal_basis": "consent",
        "data_categories": ["email"],
        "special_categories": [],
        "data_subject_types": ["customers"],
        "retention_period": "2 years",
        "recipients": ["internal"],
        "international_transfers": False,
        "status": "active",
        "risk_level": "low",
        "owner_id": owner_id,
        "linked_data_asset_ids": [],
        "linked_subprocessor_ids": [],
    }
    payload.update(overrides)
    response = client.post(f"{ROPA_BASE}/activities", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _configure_ingest_key(client, headers: dict[str, str], key: str = "privacy-ingest-key-12345") -> str:
    response = client.post(
        f"{LINEAGE_BASE}/openmetadata/configure",
        headers=headers,
        json={
            "base_url": "https://openmetadata.example.test",
            "jwt_token": "test-token",
            "org_api_key": key,
        },
    )
    assert response.status_code == 200
    return response.json()["ingest_api_key"]


def test_d88_notice_versioning_and_acknowledgement(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d88-org")

    first = _create_notice(client, org["org_headers"], title="Privacy Notice v1", content="v1")
    assert first["content_hash"]

    publish_first = client.post(f"{NOTICES_BASE}/{first['id']}/publish", headers=org["org_headers"])
    assert publish_first.status_code == 200
    assert publish_first.json()["status"] == "published"

    second = _create_notice(client, org["org_headers"], title="Privacy Notice v2", content="v2")
    publish_second = client.post(f"{NOTICES_BASE}/{second['id']}/publish", headers=org["org_headers"])
    assert publish_second.status_code == 200
    assert publish_second.json()["status"] == "published"

    # Ensure the previous published notice was archived.
    from app.models.privacy_notice import PrivacyNotice

    first_db = db_session.query(PrivacyNotice).filter(PrivacyNotice.id == uuid.UUID(first["id"])).first()
    assert first_db is not None
    assert first_db.status == "archived"

    active = client.get(f"{NOTICES_BASE}/active", headers=org["org_headers"])
    assert active.status_code == 200
    assert active.json()["id"] == second["id"]

    ack = client.post(f"{NOTICES_BASE}/{second['id']}/acknowledge", headers=org["org_headers"])
    assert ack.status_code == 200

    ack_again = client.post(f"{NOTICES_BASE}/{second['id']}/acknowledge", headers=org["org_headers"])
    assert ack_again.status_code == 200

    ack_rows = (
        db_session.query(NoticeUserAcknowledgement)
        .filter(
            NoticeUserAcknowledgement.organization_id == uuid.UUID(org["organization_id"]),
            NoticeUserAcknowledgement.notice_id == uuid.UUID(second["id"]),
            NoticeUserAcknowledgement.user_id == uuid.UUID(org["user_id"]),
        )
        .all()
    )
    assert len(ack_rows) == 1

    status_resp = client.get(f"{NOTICES_BASE}/{second['id']}/acknowledgements", headers=org["org_headers"])
    assert status_resp.status_code == 200
    body = status_resp.json()
    assert body["acknowledged_count"] >= 1
    assert body["acknowledgement_rate_pct"] >= 0


def test_d85_consent_lifecycle_inbound_and_expiry(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d85-org")

    ingest_key = _configure_ingest_key(client, org["org_headers"])

    activity = _create_processing_activity(client, org["org_headers"], org["user_id"])

    # Record consent (JWT endpoint).
    rec = client.post(
        CONSENT_BASE,
        headers=org["org_headers"],
        json={
            "processing_activity_id": activity["id"],
            "subject_identifier": "subject-123",
            "consent_mechanism": "explicit_checkbox",
            "granted": True,
            "metadata": {"channel": "web"},
        },
    )
    assert rec.status_code == 201
    rec_body = rec.json()
    assert rec_body["subject_identifier_hash"] == ConsentService.hash_subject_identifier("subject-123")

    # Same subject+activity should upsert, not duplicate.
    rec2 = client.post(
        CONSENT_BASE,
        headers=org["org_headers"],
        json={
            "processing_activity_id": activity["id"],
            "subject_identifier": "subject-123",
            "consent_mechanism": "explicit_checkbox",
            "granted": True,
            "metadata": {"channel": "app"},
        },
    )
    assert rec2.status_code == 201

    rows = (
        db_session.query(ConsentRecord)
        .filter(
            ConsentRecord.organization_id == uuid.UUID(org["organization_id"]),
            ConsentRecord.processing_activity_id == uuid.UUID(activity["id"]),
            ConsentRecord.subject_identifier_hash == ConsentService.hash_subject_identifier("subject-123"),
        )
        .all()
    )
    assert len(rows) == 1

    # Withdrawal propagation to data asset owners.
    asset = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "consent_asset",
            "asset_type": "table",
            "owner_id": org["user_id"],
            "schema_column_names": ["email"],
        },
    )
    assert asset.status_code == 201

    updated_activity = client.patch(
        f"{ROPA_BASE}/activities/{activity['id']}",
        headers=org["org_headers"],
        json={"linked_data_asset_ids": [asset.json()["id"]]},
    )
    assert updated_activity.status_code == 200

    withdraw = client.post(
        f"{CONSENT_BASE}/{rec_body['id']}/withdraw",
        headers=org["org_headers"],
        json={"reason": "user requested withdrawal"},
    )
    assert withdraw.status_code == 200
    assert withdraw.json()["granted"] is False
    assert withdraw.json()["withdrawn_at"] is not None

    outbox = (
        db_session.query(EmailOutbox)
        .filter(
            EmailOutbox.organization_id == uuid.UUID(org["organization_id"]),
            EmailOutbox.event_type == "consent.withdrawn",
        )
        .all()
    )
    assert len(outbox) >= 1

    status_true = client.get(
        f"{CONSENT_BASE}/status",
        headers=org["org_headers"],
        params={"activity_id": activity["id"], "subject_identifier": "subject-123"},
    )
    assert status_true.status_code == 200
    assert status_true.json()["has_consent"] is False

    # Inbound endpoint requires API key and no JWT.
    inbound = client.post(
        f"{CONSENT_BASE}/events",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "processing_activity_id": activity["id"],
            "subject_identifier": "subject-456",
            "consent_mechanism": "api_consent",
            "granted": True,
            "metadata": {"source": "webhook"},
        },
    )
    assert inbound.status_code == 201

    bad_inbound = client.post(
        f"{CONSENT_BASE}/events",
        headers={"X-CompliVibe-Key": "wrong-key"},
        json={
            "processing_activity_id": activity["id"],
            "subject_identifier": "subject-789",
            "consent_mechanism": "api_consent",
            "granted": True,
            "metadata": {},
        },
    )
    assert bad_inbound.status_code == 401

    # Expiry sweep marks granted consent as withdrawn.
    inbound_id = uuid.UUID(inbound.json()["id"])
    row = db_session.query(ConsentRecord).filter(ConsentRecord.id == inbound_id).first()
    assert row is not None
    row.expiry_date = date.today() - timedelta(days=1)
    row.granted = True
    row.withdrawn_at = None
    row.withdrawal_reason = None
    db_session.commit()

    sweep = ConsentService(db_session).sweep_expired_consents()
    assert sweep["expired"] >= 1

    refreshed = db_session.query(ConsentRecord).filter(ConsentRecord.id == inbound_id).first()
    assert refreshed is not None
    assert refreshed.granted is False
    assert refreshed.withdrawal_reason == "expired"


def test_t1_15_google_consent_mode_v2_signal_handling(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t115-gcm")

    response = client.post(
        f"{CONSENT_BASE}/google-consent-mode-v2",
        headers=org["org_headers"],
        json={
            "subject_identifier": "browser-user-123",
            "domain": "Example.COM",
            "url": "https://example.com/pricing",
            "region": "EEA",
            "client_id": "GA1.2.12345",
            "session_id": "session-123",
            "event_name": "consent_update",
            "ad_storage": "denied",
            "analytics_storage": "granted",
            "ad_user_data": "denied",
            "ad_personalization": "denied",
            "metadata": {"banner_version": "2026.07"},
        },
    )
    assert response.status_code == 201
    body = response.json()
    expected_hash = ConsentService.hash_subject_identifier("browser-user-123")
    assert body["subject_identifier_hash"] == expected_hash
    assert body["domain"] == "example.com"
    assert body["ad_storage"] == "denied"
    assert body["analytics_storage"] == "granted"
    assert body["ad_user_data"] == "denied"
    assert body["ad_personalization"] == "denied"
    assert "browser-user-123" not in str(body["raw_payload_json"])

    rows = (
        db_session.query(GoogleConsentModeEvent)
        .filter(
            GoogleConsentModeEvent.organization_id == uuid.UUID(org["organization_id"]),
            GoogleConsentModeEvent.subject_identifier_hash == expected_hash,
        )
        .all()
    )
    assert len(rows) == 1
    assert rows[0].raw_payload_json["states"]["analytics_storage"] == "granted"

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "consent.google_consent_mode_v2_recorded",
        )
        .one_or_none()
    )
    assert audit is not None
    assert audit.after_json["states"]["ad_user_data"] == "denied"

    listed = client.get(
        f"{CONSENT_BASE}/google-consent-mode-v2",
        headers=org["org_headers"],
        params={"domain": "example.com", "subject_identifier": "browser-user-123"},
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    invalid = client.post(
        f"{CONSENT_BASE}/google-consent-mode-v2",
        headers=org["org_headers"],
        json={
            "subject_identifier": "browser-user-123",
            "domain": "example.com",
            "ad_storage": "pending",
            "analytics_storage": "granted",
            "ad_user_data": "denied",
            "ad_personalization": "denied",
        },
    )
    assert invalid.status_code == 422
    assert "granted" in invalid.text
    assert "denied" in invalid.text


def test_d88_draft_notice_acknowledgement_blocked_until_published(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d88-draft-ack")

    draft = _create_notice(client, org["org_headers"], title="Draft Notice", content="draft content")
    assert draft["status"] == "draft"

    ack_draft = client.post(f"{NOTICES_BASE}/{draft['id']}/acknowledge", headers=org["org_headers"])
    assert ack_draft.status_code == 422
    assert "published" in ack_draft.json()["detail"].lower()

    publish = client.post(f"{NOTICES_BASE}/{draft['id']}/publish", headers=org["org_headers"])
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"

    ack_published = client.post(f"{NOTICES_BASE}/{draft['id']}/acknowledge", headers=org["org_headers"])
    assert ack_published.status_code == 200
    assert ack_published.json()["notice_id"] == draft["id"]
def test_item3_subject_identifier_is_real_one_way_hash_not_literal_placeholder(client):
    org = bootstrap_org_user(client, email_prefix="item3-hash")
    activity = _create_processing_activity(client, org["org_headers"], org["user_id"])

    def _record(subject_identifier: str, activity_id: str):
        response = client.post(
            CONSENT_BASE,
            headers=org["org_headers"],
            json={
                "processing_activity_id": activity_id,
                "subject_identifier": subject_identifier,
                "consent_mechanism": "explicit_checkbox",
                "granted": True,
            },
        )
        assert response.status_code == 201
        return response.json()

    activity2 = _create_processing_activity(client, org["org_headers"], org["user_id"], name="Second Activity")

    rec_a = _record("subject-alpha", activity["id"])
    rec_b = _record("subject-alpha", activity2["id"])
    rec_c = _record("subject-beta", activity["id"])

    assert rec_a["subject_identifier"] != "hashed"
    assert rec_a["subject_identifier"] == ConsentService.hash_subject_identifier("subject-alpha")
    # Same subject identifier -> same stored hash, consistent across repeat calls.
    assert rec_a["subject_identifier"] == rec_b["subject_identifier"]
    # Different subject identifier -> different stored hash.
    assert rec_a["subject_identifier"] != rec_c["subject_identifier"]


def test_d87_cookie_registry_scan_and_public_banner(client, db_session):
    org = bootstrap_org_user(client, email_prefix="d87-org")
    ingest_key = _configure_ingest_key(client, org["org_headers"], key="cookie-scan-key-12345")

    created = client.post(
        f"{COOKIES_BASE}/cookies",
        headers=org["org_headers"],
        json={
            "name": "manual_cookie",
            "domain": "example.com",
            "category": "functional",
            "purpose": "Preferences",
            "provider": "CompliVibe",
            "duration": "Session",
            "is_third_party": False,
        },
    )
    assert created.status_code == 201
    assert created.json()["source"] == "manual"

    scan1 = client.post(
        f"{COOKIES_BASE}/cookie-registry/scan-report",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "domain": "example.com",
            "cookies": [
                {
                    "name": "ga_cookie",
                    "category": "analytics",
                    "purpose": "Analytics",
                    "provider": "Google",
                    "duration": "1 year",
                    "is_third_party": True,
                },
                {
                    "name": "ga_cookie",
                    "category": "analytics",
                    "purpose": "Analytics",
                    "provider": "Google",
                    "duration": "1 year",
                    "is_third_party": True,
                },
            ],
            "scanned_at": datetime.now(UTC).isoformat(),
        },
    )
    assert scan1.status_code == 201

    ga_row = (
        db_session.query(CookieRegistry)
        .filter(
            CookieRegistry.organization_id == uuid.UUID(org["organization_id"]),
            CookieRegistry.name == "ga_cookie",
            CookieRegistry.domain == "example.com",
        )
        .first()
    )
    assert ga_row is not None
    assert ga_row.source == "scan_report"
    first_seen = ga_row.first_seen_at
    assert ga_row.last_seen_at is not None

    scan2 = client.post(
        f"{COOKIES_BASE}/cookie-registry/scan-report",
        headers={"X-CompliVibe-Key": ingest_key},
        json={
            "domain": "example.com",
            "cookies": [
                {
                    "name": "ga_cookie",
                    "category": "analytics",
                    "purpose": "Analytics",
                    "provider": "Google",
                    "duration": "1 year",
                    "is_third_party": True,
                },
                {
                    "name": "new_marketing_cookie",
                    "category": "marketing",
                    "purpose": "Ads",
                    "provider": "AdNet",
                    "duration": "30 days",
                    "is_third_party": True,
                },
            ],
            "scanned_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        },
    )
    assert scan2.status_code == 201

    ga_row2 = (
        db_session.query(CookieRegistry)
        .filter(
            CookieRegistry.organization_id == uuid.UUID(org["organization_id"]),
            CookieRegistry.name == "ga_cookie",
            CookieRegistry.domain == "example.com",
        )
        .first()
    )
    assert ga_row2 is not None
    assert ga_row2.first_seen_at == first_seen

    banner = client.post(
        f"{COOKIES_BASE}/banner-config",
        headers=org["org_headers"],
        json={
            "banner_title": "Cookie Preferences",
            "banner_body": "Manage cookies",
            "enabled_categories": ["strictly_necessary", "analytics", "marketing"],
            "is_active": True,
        },
    )
    assert banner.status_code == 200

    orgs = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert orgs.status_code == 200
    slug = orgs.json()[0]["slug"]

    public = client.get(f"{COOKIES_BASE}/consent-banner/{slug}")
    assert public.status_code == 200
    body = public.json()
    assert body["organization_slug"] == slug
    assert isinstance(body["cookie_categories"], list)
    assert "analytics" in body["cookie_categories"]
