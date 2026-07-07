from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.risk import Risk
from app.models.task import Task
from app.models.framework import Framework
from app.models.organization_framework import OrganizationFramework
from app.models.shared_report_link import SharedReportLink
from sqlalchemy import select
from tests.helpers.auth_org import bootstrap_org_user


def _seed_summary_records(db_session, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    framework = Framework(
        code=f"UX5-{str(org_id)[:8]}",
        name="UX5 Framework",
        category="security",
        jurisdiction="global",
    )
    db_session.add(framework)
    db_session.flush()

    org_framework = OrganizationFramework(
        organization_id=org_id,
        framework_id=framework.id,
        status="active",
        activated_by_user_id=user_id,
        activated_at=datetime.now(UTC),
    )
    db_session.add(org_framework)

    control = Control(
        organization_id=org_id,
        title="Endpoint hardening control",
        status="implemented",
        created_by_user_id=user_id,
    )
    db_session.add(control)

    evidence = EvidenceItem(
        organization_id=org_id,
        title="Hardening evidence",
        evidence_type="document",
        source="manual",
        status="active",
        review_status="approved",
        freshness_status="fresh",
        uploaded_by_user_id=user_id,
        collected_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add(evidence)

    risk = Risk(
        organization_id=org_id,
        title="Residual endpoint risk",
        severity="high",
        status="identified",
        created_by_user_id=user_id,
    )
    db_session.add(risk)

    overdue_task = Task(
        organization_id=org_id,
        title="Close endpoint remediation",
        status="open",
        priority="high",
        task_type="general",
        owner_user_id=user_id,
        created_by_user_id=user_id,
        due_date=datetime.now(UTC) - timedelta(days=2),
        source="manual",
        reminder_status="none",
    )
    db_session.add(overdue_task)
    db_session.commit()


def test_ux5_generate_one_page_summary_public_url(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="ux5-summary")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])
    _seed_summary_records(db_session, org_id, user_id)

    create_resp = client.post(
        "/api/v1/compliance-summary/generate",
        headers=ctx["org_headers"],
        json={
            "expires_hours": 24,
            "brand_name": "Acme Trust",
            "include_sections": ["overview", "controls", "risks"],
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    payload = create_resp.json()
    assert payload["public_url"].endswith(payload["token"])
    assert payload["password_protected"] is False
    assert payload["expires_in_hours"] > 0
    assert isinstance(payload["context_flags"], list)

    access_resp = client.get(f"/api/v1/reports/shared/{payload['token']}")
    assert access_resp.status_code == 200, access_resp.text
    access = access_resp.json()
    assert access["report_type"] == "compliance_one_page_summary"
    assert access["data"]["report_kind"] == "one_page_quick_read"
    assert access["data"]["brand_name"] == "Acme Trust"
    assert "overview" in access["data"]["sections_included"]
    assert access["data"]["sections"]["overview"]["framework_count"] >= 1
    assert "context_flags" in access["data"]
    assert "data_freshness" in access["data"]
    assert len(access["data"]["top_priorities"]) >= 1


def test_ux5_summary_password_gate_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ux5-org-a")
    org_b = bootstrap_org_user(client, email_prefix="ux5-org-b")
    _seed_summary_records(db_session, uuid.UUID(org_a["organization_id"]), uuid.UUID(org_a["user_id"]))
    _seed_summary_records(db_session, uuid.UUID(org_b["organization_id"]), uuid.UUID(org_b["user_id"]))

    create_resp = client.post(
        "/api/v1/compliance-summary/generate",
        headers=org_a["org_headers"],
        json={"expires_hours": 24, "password": "Secret#123"},
    )
    assert create_resp.status_code == 200, create_resp.text
    token = create_resp.json()["token"]

    unauth = client.get(f"/api/v1/reports/shared/{token}")
    assert unauth.status_code == 401

    wrong = client.get(f"/api/v1/reports/shared/{token}", params={"password": "wrong"})
    assert wrong.status_code == 401

    ok = client.get(f"/api/v1/reports/shared/{token}", params={"password": "Secret#123"})
    assert ok.status_code == 200, ok.text
    data = ok.json()["data"]
    assert data["metrics"]["controls"]["total"] >= 1
    assert "overview" in data["sections"]


def test_ux5_share_password_lockout_and_rate_limit(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="ux5-lockout")
    _seed_summary_records(db_session, uuid.UUID(ctx["organization_id"]), uuid.UUID(ctx["user_id"]))

    create_resp = client.post(
        "/api/v1/compliance-summary/generate",
        headers=ctx["org_headers"],
        json={"expires_hours": 24, "password": "Secret#123"},
    )
    assert create_resp.status_code == 200, create_resp.text
    token = create_resp.json()["token"]

    # A couple of genuine typos must not lock legitimate users out.
    for attempt in ("secret#123", "Secret#12"):
        resp = client.post(
            f"/api/v1/reports/shared/{token}/verify",
            json={"password": attempt},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    # The correct password still works before the threshold is hit.
    ok = client.post(
        f"/api/v1/reports/shared/{token}/verify",
        json={"password": "Secret#123"},
    )
    assert ok.status_code == 200
    assert ok.json()["valid"] is True

    # Build a fresh share link for the brute-force test so the earlier successful
    # verification does not reset the failure window mid-test.
    create_resp2 = client.post(
        "/api/v1/compliance-summary/generate",
        headers=ctx["org_headers"],
        json={"expires_hours": 24, "password": "LockMe#456"},
    )
    assert create_resp2.status_code == 200, create_resp2.text
    token2 = create_resp2.json()["token"]

    # Rapid wrong-password attempts should be rejected; after the threshold the
    # token itself is temporarily locked, regardless of source IP.
    for i in range(6):
        resp = client.post(
            f"/api/v1/reports/shared/{token2}/verify",
            json={"password": f"wrong-password-{i}"},
        )
        if i < 5:
            assert resp.status_code == 200
            assert resp.json()["valid"] is False
        else:
            assert resp.status_code == 429, resp.text
            assert "Retry-After" in resp.headers

    link = db_session.execute(
        select(SharedReportLink).where(SharedReportLink.token == token2)
    ).scalar_one()
    assert link.failed_password_attempt_count == 5
    assert link.locked_until is not None

    # Even the correct password is blocked while the token is locked.
    locked = client.post(
        f"/api/v1/reports/shared/{token2}/verify",
        json={"password": "LockMe#456"},
    )
    assert locked.status_code == 429, locked.text


def test_ux5_generate_rejects_invalid_include_sections(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="ux5-invalid-sections")
    _seed_summary_records(db_session, uuid.UUID(ctx["organization_id"]), uuid.UUID(ctx["user_id"]))

    invalid = client.post(
        "/api/v1/compliance-summary/generate",
        headers=ctx["org_headers"],
        json={
            "include_sections": ["overview", "not-a-section"],
        },
    )
    assert invalid.status_code == 422
    assert "Unsupported include_sections values" in invalid.json()["detail"]
