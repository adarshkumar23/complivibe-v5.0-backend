"""Regression tests for email send-cap + recipient gating (2026-07-20).

SES is in PRODUCTION, so the abuse surface is real:
  * OrgEmailConfig.daily_send_limit / sent_today existed but were dead -- no per-org cap
    was enforced, so an email:write holder could queue unlimited mail.
  * POST /email/outbox accepted any recipient address with only email:write.
  * POST /admin/email-config/test sent to a caller-supplied arbitrary address.
  * Email endpoints fell through to the loose api_general (300/min) rate-limit bucket.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.core.rate_limiter import ENDPOINT_GROUP_DEFAULTS, CompliVibeRateLimiter
from app.models.email_outbox import EmailOutbox
from app.models.org_email_config import OrgEmailConfig
from app.platform.services.email_outbox_flush_service import EmailOutboxFlushService
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

pytestmark = pytest.mark.usefixtures("seeded_reference_data")

OUTBOX = "/api/v1/email/outbox"


def _global_template_key(client, headers) -> str:
    templates = client.get("/api/v1/email/templates", headers=headers).json()
    return next(t["template_key"] for t in templates if t["template_key"] == "invited_user_activation")


def _make_email_config(db_session, org_id: str, user_id: str, *, daily_limit: int) -> None:
    now = datetime.now(UTC)
    db_session.add(
        OrgEmailConfig(
            organization_id=uuid.UUID(org_id),
            provider="ses",
            config_json="{}",
            is_active=True,
            use_platform_ses=True,
            daily_send_limit=daily_limit,
            sent_today=0,
            created_by=uuid.UUID(user_id),
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def test_daily_send_cap_is_enforced_in_the_drain(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="mailcap")
    _make_email_config(db_session, org["organization_id"], org["user_id"], daily_limit=1)
    tpl_key = _global_template_key(client, org["org_headers"])

    # Queue two emails to the org owner (a member -> allowed).
    for i in range(2):
        resp = client.post(
            OUTBOX,
            headers=org["org_headers"],
            json={
                "template_key": tpl_key,
                "recipient_email": org["email"],
                "event_type": "invitation.created",
                "variables_json": {"user_name": "Owner", "activation_link": "https://x"},
            },
        )
        assert resp.status_code == 201, resp.text

    service = EmailOutboxFlushService(db_session)
    monkeypatch.setattr(service.ses, "send_email", lambda **kwargs: {"success": True, "message_id": "m"})
    result = service.flush()
    db_session.commit()

    # Exactly one sent; the second is deferred, not sent, because the org's cap is 1/day.
    assert result["sent"] == 1, result
    statuses = sorted(
        s for (s,) in db_session.query(EmailOutbox.status).filter(
            EmailOutbox.organization_id == uuid.UUID(org["organization_id"])
        )
    )
    assert statuses == ["pending", "sent"]
    cfg = db_session.query(OrgEmailConfig).filter(
        OrgEmailConfig.organization_id == uuid.UUID(org["organization_id"])
    ).one()
    assert cfg.sent_today == 1

    # Re-draining immediately does not push past the cap.
    result2 = service.flush()
    db_session.commit()
    assert result2["sent"] == 0, result2
    assert cfg.sent_today == 1


def test_outbox_external_recipient_requires_email_admin(client, db_session):
    org = bootstrap_org_user(client, email_prefix="mailrcpt")
    # compliance_manager holds email:write but NOT email:admin.
    cm_headers = add_org_member(
        db_session, client, org["organization_id"], "mailrcpt-cm@example.com", role_name="compliance_manager"
    )
    tpl_key = _global_template_key(client, org["org_headers"])
    body = {
        "template_key": tpl_key,
        "event_type": "invitation.created",
        "variables_json": {"user_name": "X", "activation_link": "https://x"},
    }

    # email:write -> external (non-member) address is rejected.
    external = client.post(OUTBOX, headers=cm_headers, json={**body, "recipient_email": "outsider@evil.example"})
    assert external.status_code == 403, external.text
    assert "email:admin" in external.json()["detail"]

    # email:write -> a member's address is allowed.
    to_member = client.post(OUTBOX, headers=cm_headers, json={**body, "recipient_email": org["email"]})
    assert to_member.status_code == 201, to_member.text

    # email:admin (owner) -> external address is allowed.
    owner_external = client.post(OUTBOX, headers=org["org_headers"], json={**body, "recipient_email": "outsider@evil.example"})
    assert owner_external.status_code == 201, owner_external.text


def test_admin_test_send_ignores_caller_supplied_recipient(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="mailtest")
    _make_email_config(db_session, org["organization_id"], org["user_id"], daily_limit=1000)
    # Deterministic send (SES is real/prod; no creds in the test env). We only assert
    # WHERE it would send, not that it reached AWS.
    from app.platform.services.ses_service import SESService

    captured: dict = {}

    def _fake_send(self, **kwargs):
        captured["to_email"] = kwargs.get("to_email")
        return {"success": True, "message_id": "m"}

    monkeypatch.setattr(SESService, "send_email", _fake_send)

    resp = client.post(
        "/api/v1/admin/email-config/test",
        headers=org["org_headers"],
        json={"to_address": "attacker@evil.example"},
    )
    assert resp.status_code == 200, resp.text
    # The test send goes to the caller's own email, never the supplied arbitrary address.
    assert resp.json()["sent_to"] == org["email"]
    assert resp.json()["sent_to"] != "attacker@evil.example"
    assert captured.get("to_email") == org["email"]


def test_email_endpoints_have_a_dedicated_tight_rate_limit_group():
    assert CompliVibeRateLimiter.endpoint_group_for_path("/api/v1/email/outbox") == "email"
    assert CompliVibeRateLimiter.endpoint_group_for_path("/api/v1/email/templates") == "email"
    assert CompliVibeRateLimiter.endpoint_group_for_path("/api/v1/admin/email-config/test") == "email"
    # Tighter than the loose api_general bucket it used to fall through to.
    assert ENDPOINT_GROUP_DEFAULTS["email"] == "20/minute"
    assert ENDPOINT_GROUP_DEFAULTS["email"] != ENDPOINT_GROUP_DEFAULTS["api_general"]
