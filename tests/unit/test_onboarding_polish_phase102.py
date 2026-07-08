from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.models.framework import Framework
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from tests.helpers.auth_org import bootstrap_org_user


def test_checklist_reports_next_step_and_is_not_stalled_for_new_org(client):
    ctx = bootstrap_org_user(client, email_prefix="onb-polish-next")
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    response = client.get("/api/v1/onboarding/checklist", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["completion_percentage"] < 100
    assert body["next_step"] is not None
    assert body["next_step"]["completed"] is False
    assert body["stalled"] is False
    assert body["days_since_created"] == 0
    assert "onboarding_stalled" not in body["context_flags"]


def test_checklist_flags_stalled_onboarding_after_a_week(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="onb-polish-stalled")
    org_id = UUID(ctx["organization_id"])
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    org = db_session.get(Organization, org_id)
    org.created_at = datetime.now(UTC) - timedelta(days=10)
    db_session.commit()

    response = client.get("/api/v1/onboarding/checklist", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["stalled"] is True
    assert body["days_since_created"] >= 10
    assert "onboarding_stalled" in body["context_flags"]


def test_checklist_flags_ready_to_complete_when_all_core_items_done(client, db_session):
    from app.models.control import Control
    from app.models.membership import Membership
    from app.models.risk import Risk
    from app.models.user import User

    ctx = bootstrap_org_user(client, email_prefix="onb-polish-ready")
    org_id = UUID(ctx["organization_id"])
    user_id = UUID(ctx["user_id"])
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    framework = Framework(code="ONB-READY", name="Onboard Ready FW", category="security", jurisdiction="global", status="active")
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(organization_id=org_id, framework_id=framework.id, status="active", activated_by_user_id=user_id)
    )

    extra_user = User(email="ready-member@example.com", full_name="Ready Member", hashed_password="x", is_active=True, status="active", is_superuser=False)
    db_session.add(extra_user)
    db_session.flush()
    owner_membership = db_session.query(Membership).filter(Membership.organization_id == org_id, Membership.user_id == user_id).one()
    db_session.add(Membership(organization_id=org_id, user_id=extra_user.id, role_id=owner_membership.role_id, status="active", invited_by=user_id))

    db_session.add(Control(organization_id=org_id, title="C1", control_type="process", status="implemented", criticality="medium", source="custom"))
    db_session.add(
        Risk(
            organization_id=org_id,
            title="R1",
            category="security",
            severity="high",
            likelihood=3,
            impact=3,
            inherent_score=9,
            status="identified",
            treatment_strategy="mitigate",
            composite_score_method="standard",
        )
    )
    db_session.commit()

    response = client.get("/api/v1/onboarding/checklist", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["completion_percentage"] == 100
    assert body["next_step"] is not None  # evidence_uploaded is outside the core percentage but still tracked
    assert "ready_to_complete" in body["context_flags"]


def test_complete_onboarding_requires_framework_selection(client):
    ctx = bootstrap_org_user(client, email_prefix="onb-polish-guard")
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    response = client.post("/api/v1/onboarding/complete", headers=headers)
    assert response.status_code == 400
    assert "framework" in response.json()["detail"].lower()


def test_complete_onboarding_is_idempotent_and_preserves_original_timestamp(client, db_session):
    ctx = bootstrap_org_user(client, email_prefix="onb-polish-idempotent")
    org_id = UUID(ctx["organization_id"])
    user_id = UUID(ctx["user_id"])
    headers = {"Authorization": f"Bearer {ctx['access_token']}", "X-Organization-ID": ctx["organization_id"]}

    framework = Framework(code="ONB-IDEMP", name="Idempotent FW", category="security", jurisdiction="global", status="active")
    db_session.add(framework)
    db_session.flush()
    db_session.add(
        OrganizationFramework(organization_id=org_id, framework_id=framework.id, status="active", activated_by_user_id=user_id)
    )
    db_session.commit()

    first = client.post("/api/v1/onboarding/complete", headers=headers)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["onboarding_completed"] is True
    assert first_body["already_completed"] is False
    first_completed_at = first_body["completed_at"]

    second = client.post("/api/v1/onboarding/complete", headers=headers)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["already_completed"] is True

    def _as_utc(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    # SQLite (the test DB) doesn't round-trip tzinfo faithfully, so compare instants rather
    # than raw strings; the real guarantee under test is that the timestamp did not advance.
    assert _as_utc(second_body["completed_at"]) == _as_utc(first_completed_at)
