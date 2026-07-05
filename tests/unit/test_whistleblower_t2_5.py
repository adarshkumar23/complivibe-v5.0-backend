from __future__ import annotations

import hashlib
import uuid

import sqlalchemy as sa

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.models.whistleblower import WhistleblowerMessage, WhistleblowerReport
from tests.helpers.auth_org import bootstrap_org_user, org_headers


def _create_active_user_with_role(db_session, organization_id: str, email: str, role_name: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()

    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(organization_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(organization_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def _login(client, email: str, password: str = "Pass1234!@") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _submit(client, organization_id: str, **overrides):
    payload = {
        "organization_id": organization_id,
        "category": "fraud",
        "description": "Someone is falsifying expense reports.",
    }
    payload.update(overrides)
    return client.post("/api/v1/whistleblower/submit", json=payload)


def test_whistleblower_permissions_seeded(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-perms")

    rows = db_session.execute(
        sa.text("SELECT key FROM permissions WHERE key LIKE 'whistleblower:%'")
    ).scalars().all()
    assert set(rows) == {"whistleblower:investigate"}, "only whistleblower:investigate should exist, no whistleblower:manage"

    response = client.get("/api/v1/auth/permissions", headers=org_user["org_headers"])
    assert response.status_code == 200, response.text
    codes = response.json()["permission_codes"]
    assert "whistleblower:investigate" in codes


def test_public_submit_happy_path_no_auth(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-submit")
    organization_id = org_user["organization_id"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert set(body.keys()) == {"tracking_code", "anonymous_id", "warning"}
    assert body["tracking_code"]
    assert body["anonymous_id"]
    assert body["tracking_code"] != body["anonymous_id"]


def test_anonymity_proof(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-anon")
    organization_id = org_user["organization_id"]

    resp = _submit(client, organization_id, description="Confidential fraud details here.")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    tracking_code = body["tracking_code"]
    anonymous_id = body["anonymous_id"]

    report = db_session.execute(
        sa.select(WhistleblowerReport).where(WhistleblowerReport.anonymous_id == anonymous_id)
    ).scalar_one()

    expected_hash = hashlib.sha256(tracking_code.encode("utf-8")).hexdigest()
    assert report.tracking_code_hash == expected_hash
    assert report.tracking_code_hash != tracking_code

    column_names = {c.name for c in WhistleblowerReport.__table__.columns}
    for forbidden in ("ip_address", "session", "submitter", "created_by"):
        assert not any(forbidden in name for name in column_names), (
            f"found forbidden identity-linked column pattern '{forbidden}' in {column_names}"
        )
    assert "assigned_investigator_user_id" in column_names  # investigator FK is fine

    audit_row = db_session.execute(
        sa.select(AuditLog).where(
            AuditLog.entity_type == "whistleblower_report",
            AuditLog.entity_id == report.id,
            AuditLog.action == "whistleblower_report.submitted",
        )
    ).scalar_one()
    assert audit_row.actor_user_id is None
    assert audit_row.ip_address is None
    assert audit_row.user_agent is None
    serialized = str(audit_row.after_json) + str(audit_row.before_json) + str(audit_row.metadata_json)
    assert "@" not in serialized  # no email
    assert tracking_code not in serialized  # raw tracking code never stored


def test_status_lookup_correct_and_wrong_code(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-status")
    organization_id = org_user["organization_id"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text
    tracking_code = resp.json()["tracking_code"]

    ok = client.get(f"/api/v1/whistleblower/status/{tracking_code}")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["category"] == "fraud"
    assert body["status"] == "submitted"
    assert body["messages"] == []

    bad = client.get("/api/v1/whistleblower/status/not-a-real-tracking-code")
    assert bad.status_code == 404, bad.text


def test_reporter_reply_creates_anonymous_message(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-reply")
    organization_id = org_user["organization_id"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text
    tracking_code = resp.json()["tracking_code"]

    reply = client.post(
        f"/api/v1/whistleblower/status/{tracking_code}/reply",
        json={"content": "Additional detail from reporter."},
    )
    assert reply.status_code == 201, reply.text

    message = db_session.execute(
        sa.select(WhistleblowerMessage).where(WhistleblowerMessage.content == "Additional detail from reporter.")
    ).scalar_one()
    assert message.sender_type == "reporter"
    assert message.sender_user_id is None


def test_investigator_can_list_reply_and_update_status(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-invest")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text
    tracking_code = resp.json()["tracking_code"]

    listing = client.get("/api/v1/whistleblower/reports", headers=headers)
    assert listing.status_code == 200, listing.text
    reports = listing.json()
    assert len(reports) == 1
    report_id = reports[0]["id"]

    reply = client.post(
        f"/api/v1/whistleblower/reports/{report_id}/reply",
        headers=headers,
        json={"content": "We are looking into this."},
    )
    assert reply.status_code == 201, reply.text

    message = db_session.execute(
        sa.select(WhistleblowerMessage).where(WhistleblowerMessage.content == "We are looking into this.")
    ).scalar_one()
    assert message.sender_type == "investigator"
    assert str(message.sender_user_id) == org_user["user_id"]

    status_resp = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "under_review"},
    )
    assert status_resp.status_code == 200, status_resp.text
    assert status_resp.json()["status"] == "under_review"

    # reporter-visible status endpoint should reflect the update + message thread
    reporter_view = client.get(f"/api/v1/whistleblower/status/{tracking_code}")
    assert reporter_view.status_code == 200, reporter_view.text
    assert reporter_view.json()["status"] == "under_review"
    assert len(reporter_view.json()["messages"]) == 1


def test_investigator_without_permission_gets_403(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-noperm")
    organization_id = org_user["organization_id"]

    readonly_user = _create_active_user_with_role(db_session, organization_id, "wb-readonly@example.com", "readonly")
    readonly_token = _login(client, readonly_user.email)
    headers = org_headers(readonly_token, organization_id)

    resp = client.get("/api/v1/whistleblower/reports", headers=headers)
    assert resp.status_code == 403, resp.text


def test_invalid_status_transition_returns_400(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-badtrans")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text

    reports = client.get("/api/v1/whistleblower/reports", headers=headers).json()
    report_id = reports[0]["id"]

    closed = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "resolved"},
    )
    assert closed.status_code == 400, closed.text  # submitted -> resolved is not a valid direct transition

    # Walk to a real 'closed' status via valid path, then attempt closed -> submitted.
    step1 = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "investigating"},
    )
    assert step1.status_code == 200, step1.text
    step2 = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "closed"},
    )
    assert step2.status_code == 200, step2.text

    invalid = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "submitted"},
    )
    assert invalid.status_code == 400, invalid.text


def test_invalid_category_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-badcat")
    organization_id = org_user["organization_id"]

    resp = _submit(client, organization_id, category="not_a_real_category")
    assert resp.status_code == 422, resp.text


def test_cross_org_investigator_cannot_see_other_org_reports(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="wb-orga")
    org_b = bootstrap_org_user(client, email_prefix="wb-orgb")

    resp = _submit(client, org_a["organization_id"])
    assert resp.status_code == 201, resp.text

    listing = client.get("/api/v1/whistleblower/reports", headers=org_b["org_headers"])
    assert listing.status_code == 200, listing.text
    assert listing.json() == []
