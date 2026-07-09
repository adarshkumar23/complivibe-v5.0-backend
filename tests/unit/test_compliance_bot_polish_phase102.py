from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, date, datetime, timedelta

from app.models.compliance_bot_outbox import ComplianceBotOutbox
from app.models.compliance_bot_subscription import ComplianceBotSubscription
from app.models.compliance_policy import CompliancePolicy
from app.models.organization import Organization
from app.models.policy_attestation_campaign import PolicyAttestationCampaign
from app.models.policy_attestation_record import PolicyAttestationRecord
from app.models.user import User


def _register(client, email: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!@", "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    response = client.get("/api/v1/organizations/me", headers=_headers(token))
    assert response.status_code == 200
    return response.json()[0]["id"]


def _user(db_session, email: str) -> User:
    return db_session.query(User).filter(User.email == email).one()


def _set_webhook_secret(db_session, org_id: str, secret: str = "test-webhook-secret") -> str:
    org = db_session.query(Organization).filter(Organization.id == uuid.UUID(org_id)).one()
    org.compliance_bot_webhook_secret = secret
    db_session.commit()
    return secret


def _signed_webhook_post(client, path: str, secret: str, payload: dict):
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(path, content=body, headers={"Content-Type": "application/json", "X-ComplianceBot-Signature": signature})


def _seed_policy_attestation_record(db_session, org_id: str, user: User) -> PolicyAttestationRecord:
    policy = CompliancePolicy(
        organization_id=uuid.UUID(org_id),
        title="P102 Policy",
        description="Command idempotency policy",
        policy_type="security",
        status="approved",
        owner_user_id=user.id,
        approved_by_user_id=user.id,
        version="1.0",
    )
    db_session.add(policy)
    db_session.flush()

    campaign = PolicyAttestationCampaign(
        organization_id=uuid.UUID(org_id),
        policy_id=policy.id,
        policy_version="1.0",
        name=f"P102 Campaign {org_id[:8]}",
        description="Bot idempotency campaign",
        due_date=date.today() + timedelta(days=7),
        attestation_expiry_days=30,
        status="active",
        created_by=user.id,
    )
    db_session.add(campaign)
    db_session.flush()

    record = PolicyAttestationRecord(
        organization_id=uuid.UUID(org_id),
        campaign_id=campaign.id,
        user_id=user.id,
        status="pending",
    )
    db_session.add(record)
    db_session.commit()
    return record


def test_phase102_slack_retry_with_same_trigger_id_does_not_double_approve(client, db_session):
    token = _register(client, "p102-owner-retry@example.com", "P102 Retry Org")
    org_id = _org_id(client, token)
    user = _user(db_session, "p102-owner-retry@example.com")
    record = _seed_policy_attestation_record(db_session, org_id, user)

    sub = client.post(
        "/api/v1/compliance-bot/subscriptions",
        headers=_headers(token, org_id),
        json={
            "platform": "slack",
            "channel_ref": "C-P102-ALERTS",
            "digest_enabled": True,
            "digest_time_utc": "08:00",
            "sla_alerts_enabled": True,
            "platform_user_ref": "U-SLACK-1",
        },
    )
    assert sub.status_code == 200

    secret = _set_webhook_secret(db_session, org_id)
    slack_payload = {
        "command": "/complivibe",
        "text": f"approve {record.id}",
        "channel_id": "C-P102-ALERTS",
        "user_id": "U-SLACK-1",
        "trigger_id": "T-RETRY-1234.5678",
    }

    first = _signed_webhook_post(client, f"/api/v1/compliance-bot/slack/commands/{org_id}", secret, slack_payload)
    assert first.status_code == 200, first.text
    assert first.json()["state_changed"] is True
    assert first.json()["replayed"] is False

    # Slack retries the identical delivery (same trigger_id) because our first ack was
    # slow/lost. This must not re-run submit_attestation (which would 400 on a
    # non-pending record) - it should replay the stored response instead.
    retry = _signed_webhook_post(client, f"/api/v1/compliance-bot/slack/commands/{org_id}", secret, slack_payload)
    assert retry.status_code == 200, retry.text
    retry_body = retry.json()
    assert retry_body["replayed"] is True
    assert retry_body["response_text"] == first.json()["response_text"]

    db_session.expire_all()
    updated = (
        db_session.query(PolicyAttestationRecord)
        .filter(
            PolicyAttestationRecord.organization_id == uuid.UUID(org_id),
            PolicyAttestationRecord.id == record.id,
        )
        .one()
    )
    assert updated.status == "attested"

    outbox_rows = (
        db_session.query(ComplianceBotOutbox)
        .filter(
            ComplianceBotOutbox.organization_id == uuid.UUID(org_id),
            ComplianceBotOutbox.message_type == "command_response",
        )
        .all()
    )
    # Only one outbox row is ever written for the deduped trigger_id.
    assert len(outbox_rows) == 1
    assert outbox_rows[0].idempotency_key == "T-RETRY-1234.5678"


def test_phase102_different_trigger_id_is_not_treated_as_duplicate(client, db_session):
    token = _register(client, "p102-owner-distinct@example.com", "P102 Distinct Org")
    org_id = _org_id(client, token)

    client.post(
        "/api/v1/compliance-bot/subscriptions",
        headers=_headers(token, org_id),
        json={
            "platform": "slack",
            "channel_ref": "C-P102-DISTINCT",
            "digest_enabled": True,
            "digest_time_utc": "08:00",
            "sla_alerts_enabled": True,
            "platform_user_ref": "U-SLACK-DISTINCT",
        },
    )

    secret = _set_webhook_secret(db_session, org_id)
    for trigger in ("T-A", "T-B"):
        response = _signed_webhook_post(
            client,
            f"/api/v1/compliance-bot/slack/commands/{org_id}",
            secret,
            {"command": "/complivibe", "text": "status", "trigger_id": trigger, "user_id": "U-SLACK-DISTINCT"},
        )
        assert response.status_code == 200
        assert response.json()["replayed"] is False

    outbox_rows = (
        db_session.query(ComplianceBotOutbox)
        .filter(
            ComplianceBotOutbox.organization_id == uuid.UUID(org_id),
            ComplianceBotOutbox.message_type == "command_response",
        )
        .all()
    )
    assert len(outbox_rows) == 2


def test_phase102_subscription_flags_pending_first_digest_and_stale_digest(client, db_session):
    token = _register(client, "p102-owner-stale@example.com", "P102 Stale Org")
    org_id = _org_id(client, token)
    user = _user(db_session, "p102-owner-stale@example.com")

    sub = client.post(
        "/api/v1/compliance-bot/subscriptions",
        headers=_headers(token, org_id),
        json={
            "platform": "slack",
            "channel_ref": "C-P102-STALE",
            "digest_enabled": True,
            "digest_time_utc": "08:00",
            "sla_alerts_enabled": True,
        },
    )
    assert sub.status_code == 200

    # Backdate creation so a never-triggered digest looks like it has gone dark.
    sub_row = (
        db_session.query(ComplianceBotSubscription)
        .filter(
            ComplianceBotSubscription.organization_id == uuid.UUID(org_id),
            ComplianceBotSubscription.user_id == user.id,
        )
        .one()
    )
    sub_row.created_at = datetime.now(UTC) - timedelta(days=30)
    db_session.commit()

    listing = client.get("/api/v1/compliance-bot/subscriptions", headers=_headers(token, org_id))
    assert listing.status_code == 200
    body = listing.json()[0]
    assert "digest_pending_first_send" in body["context_flags"]
    assert "sla_alerts_pending_first_check" in body["context_flags"]

    # Now simulate a digest that fired a long time ago and never again.
    sub_row.last_digest_sent_at = datetime.now(UTC) - timedelta(days=20)
    db_session.commit()

    listing2 = client.get("/api/v1/compliance-bot/subscriptions", headers=_headers(token, org_id))
    body2 = listing2.json()[0]
    assert "digest_stale" in body2["context_flags"]
    assert "digest_pending_first_send" not in body2["context_flags"]
