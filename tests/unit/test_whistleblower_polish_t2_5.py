from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.models.whistleblower import WhistleblowerReport
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


def test_retaliation_category_flagged_for_priority_handling(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-retaliation")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id, category="retaliation", description="Retaliated against for a prior report.")
    assert resp.status_code == 201, resp.text

    listing = client.get("/api/v1/whistleblower/reports", headers=headers)
    assert listing.status_code == 200, listing.text
    report = listing.json()[0]
    assert any("retaliation_category_requires_priority_handling" in f for f in report["context_flags"])


def test_acknowledgment_overdue_flag_for_stale_submitted_report(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-ack-overdue")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text

    listing = client.get("/api/v1/whistleblower/reports", headers=headers)
    report_id = listing.json()[0]["id"]

    db_report = db_session.get(WhistleblowerReport, uuid.UUID(report_id))
    db_report.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    db_session.commit()

    detail = client.get(f"/api/v1/whistleblower/reports/{report_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["days_open"] >= 10
    assert any("acknowledgment_overdue" in f for f in body["context_flags"])


def test_feedback_overdue_flag_for_long_open_report(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-feedback-overdue")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text
    listing = client.get("/api/v1/whistleblower/reports", headers=headers)
    report_id = listing.json()[0]["id"]

    # Move to an open (non-terminal) status, then backdate past the 90-day SLA.
    status_resp = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "investigating"},
    )
    assert status_resp.status_code == 200, status_resp.text

    db_report = db_session.get(WhistleblowerReport, uuid.UUID(report_id))
    db_report.created_at = datetime.now(timezone.utc) - timedelta(days=120)
    db_session.commit()

    detail = client.get(f"/api/v1/whistleblower/reports/{report_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert any("feedback_overdue" in f for f in detail.json()["context_flags"])


def test_deactivated_investigator_flagged_for_reassignment(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-inactive-investigator")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text
    listing = client.get("/api/v1/whistleblower/reports", headers=headers)
    report_id = listing.json()[0]["id"]

    status_resp = client.patch(
        f"/api/v1/whistleblower/reports/{report_id}/status",
        headers=headers,
        json={"status": "under_review"},
    )
    assert status_resp.status_code == 200, status_resp.text

    # A second investigator (who stays active) will observe the deactivation.
    second_investigator = _create_active_user_with_role(
        db_session, organization_id, "wb-second-investigator@example.com", "admin"
    )
    second_token = _login(client, second_investigator.email)
    second_headers = org_headers(second_token, organization_id)

    # Deactivate the original investigator (the org owner who just claimed the case).
    investigator = db_session.get(User, uuid.UUID(org_user["user_id"]))
    investigator.is_active = False
    db_session.commit()

    detail = client.get(f"/api/v1/whistleblower/reports/{report_id}", headers=second_headers)
    assert detail.status_code == 200, detail.text
    assert any("assigned_investigator_inactive" in f for f in detail.json()["context_flags"])


def test_reporter_status_view_never_leaks_investigator_context(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-no-leak")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id, category="retaliation")
    assert resp.status_code == 201, resp.text
    tracking_code = resp.json()["tracking_code"]

    reporter_view = client.get(f"/api/v1/whistleblower/status/{tracking_code}")
    assert reporter_view.status_code == 200, reporter_view.text
    body = reporter_view.json()
    assert "context_flags" not in body
    assert "days_open" not in body
    assert "assigned_investigator_user_id" not in body


def test_fresh_report_has_no_sla_flags(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="wb-fresh")
    organization_id = org_user["organization_id"]
    headers = org_user["org_headers"]

    resp = _submit(client, organization_id)
    assert resp.status_code == 201, resp.text

    listing = client.get("/api/v1/whistleblower/reports", headers=headers)
    assert listing.status_code == 200, listing.text
    report = listing.json()[0]
    assert report["days_open"] == 0
    assert report["context_flags"] == []
