from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app.core.security import get_password_hash
from app.models.bcm import BiaAssessment, BusinessProcess
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user


def _create_process(client, headers, **overrides):
    payload = {
        "name": "Payroll Processing",
        "description": "Bi-weekly payroll run",
        "recovery_time_objective_hours": 4,
        "recovery_point_objective_hours": 1,
        "criticality_tier": "tier_1_critical",
    }
    payload.update(overrides)
    return client.post("/api/v1/bcm/processes", headers=headers, json=payload)


def test_bcm_permissions_seeded(client, db_session):
    # Bootstrapping an org triggers SeedService.ensure_roles_for_organization,
    # which is what actually populates the permissions table in this test env
    # (the alembic migration's raw-SQL seeding only applies to a real upgrade).
    org_user = bootstrap_org_user(client, email_prefix="bcm-perms")

    rows = db_session.execute(
        sa.text("SELECT key FROM permissions WHERE key IN ('bcm:read', 'bcm:manage')")
    ).scalars().all()
    assert set(rows) == {"bcm:read", "bcm:manage"}
    response = client.get("/api/v1/auth/permissions", headers=org_user["org_headers"])
    assert response.status_code == 200, response.text
    codes = response.json()["permission_codes"]
    assert "bcm:read" in codes
    assert "bcm:manage" in codes


def test_create_process_and_bia_happy_path(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-happy")
    headers = org_user["org_headers"]

    resp = _create_process(client, headers)
    assert resp.status_code == 201, resp.text
    process = resp.json()
    process_id = process["id"]
    assert process["criticality_tier"] == "tier_1_critical"

    bia_payload = {
        "impact_analysis_json": {"financial": "high", "operational": "medium", "narrative": "test"},
        "financial_impact_tier": "high",
        "review_frequency_months": 12,
    }
    bia_resp = client.post(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers, json=bia_payload)
    assert bia_resp.status_code == 201, bia_resp.text
    bia = bia_resp.json()
    assert bia["process_id"] == process_id
    assert bia["financial_impact_tier"] == "high"

    get_resp = client.get(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    body = get_resp.json()
    assert body["latest"]["id"] == bia["id"]
    assert len(body["history"]) == 1


def test_overdue_reviews_empty_for_freshly_reviewed_process(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-fresh")
    headers = org_user["org_headers"]

    resp = _create_process(client, headers)
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    bia_payload = {
        "impact_analysis_json": {"financial": "low"},
        "review_frequency_months": 12,
    }
    bia_resp = client.post(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers, json=bia_payload)
    assert bia_resp.status_code == 201, bia_resp.text

    overdue_resp = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_resp.status_code == 200, overdue_resp.text
    items = overdue_resp.json()["items"]
    assert all(item["process_id"] != process_id for item in items)


def test_overdue_reviews_flags_stale_review_window(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-stale")
    headers = org_user["org_headers"]

    resp = _create_process(client, headers)
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    bia_payload = {
        "impact_analysis_json": {"financial": "low"},
        "review_frequency_months": 6,
    }
    bia_resp = client.post(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers, json=bia_payload)
    assert bia_resp.status_code == 201, bia_resp.text
    bia_id = bia_resp.json()["id"]

    # Directly push last_reviewed_at far into the past so the review window has lapsed.
    # Use the ORM (not a raw-SQL string comparison) since sqlalchemy.Uuid stores
    # values as unhyphenated CHAR(32) on sqlite, which a hyphenated string
    # literal in a raw WHERE clause would silently fail to match.
    far_past = datetime.now(timezone.utc) - timedelta(days=400)
    bia_row = db_session.get(BiaAssessment, uuid.UUID(bia_id))
    bia_row.last_reviewed_at = far_past
    db_session.commit()

    overdue_resp = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_resp.status_code == 200, overdue_resp.text
    items = overdue_resp.json()["items"]
    matching = [item for item in items if item["process_id"] == process_id]
    assert len(matching) == 1
    assert matching[0]["is_stale"] is True
    assert any("overdue" in reason for reason in matching[0]["stale_reasons"])


def test_overdue_reviews_flags_deactivated_owner(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-owner")
    headers = org_user["org_headers"]
    organization_id = org_user["organization_id"]

    # Use a distinct process-owner user rather than the requester, so
    # deactivating the owner doesn't also lock the requester's own session.
    owner = User(
        email="bcm-owner-target@example.com",
        full_name="BCM Owner Target",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()
    role = db_session.query(Role).filter(
        Role.organization_id == uuid.UUID(organization_id), Role.name == "reviewer"
    ).one()
    membership = Membership(
        organization_id=uuid.UUID(organization_id),
        user_id=owner.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    owner_id = str(owner.id)

    resp = _create_process(client, headers, owner_user_id=owner_id)
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    bia_payload = {
        "impact_analysis_json": {"financial": "low"},
        "review_frequency_months": 12,
    }
    bia_resp = client.post(f"/api/v1/bcm/processes/{process_id}/bia", headers=headers, json=bia_payload)
    assert bia_resp.status_code == 201, bia_resp.text

    # Deactivate the owner's account directly; review window has not lapsed.
    # Use the ORM to avoid the raw-SQL/hyphenated-UUID mismatch noted above.
    user_row = db_session.get(User, uuid.UUID(owner_id))
    user_row.is_active = False
    db_session.commit()

    overdue_resp = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_resp.status_code == 200, overdue_resp.text
    items = overdue_resp.json()["items"]
    matching = [item for item in items if item["process_id"] == process_id]
    assert len(matching) == 1
    assert matching[0]["is_stale"] is True
    assert any("deactivated" in reason for reason in matching[0]["stale_reasons"])


def test_create_process_and_bia_reject_inactive_org_user_references(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-inactive-ref")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    inactive_user = User(
        email="bcm-inactive-reference@example.com",
        full_name="Inactive BCM Reference",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(inactive_user)
    db_session.flush()
    role = db_session.query(Role).filter(Role.organization_id == organization_id, Role.name == "reviewer").one()
    db_session.add(
        Membership(
            organization_id=organization_id,
            user_id=inactive_user.id,
            role_id=role.id,
            status="inactive",
        )
    )
    db_session.commit()

    rejected_process = _create_process(
        client,
        headers,
        name="Inactive Owner Process",
        owner_user_id=str(inactive_user.id),
    )
    assert rejected_process.status_code == 400, rejected_process.text
    assert db_session.query(BusinessProcess).filter(BusinessProcess.name == "Inactive Owner Process").count() == 0

    process = _create_process(client, headers)
    assert process.status_code == 201, process.text
    rejected_bia = client.post(
        f"/api/v1/bcm/processes/{process.json()['id']}/bia",
        headers=headers,
        json={
            "impact_analysis_json": {"financial": "medium"},
            "review_frequency_months": 12,
            "reviewed_by_user_id": str(inactive_user.id),
        },
    )
    assert rejected_bia.status_code == 400, rejected_bia.text
    assert db_session.query(BiaAssessment).filter(BiaAssessment.reviewed_by_user_id == inactive_user.id).count() == 0


def test_overdue_reviews_flags_inactive_owner_membership_and_status(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-owner-membership")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    owner = User(
        email="bcm-owner-membership@example.com",
        full_name="BCM Owner Membership",
        hashed_password=get_password_hash("Pass1234!@"),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(owner)
    db_session.flush()
    role = db_session.query(Role).filter(Role.organization_id == organization_id, Role.name == "reviewer").one()
    membership = Membership(
        organization_id=organization_id,
        user_id=owner.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()

    resp = _create_process(client, headers, owner_user_id=str(owner.id))
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]
    bia_resp = client.post(
        f"/api/v1/bcm/processes/{process_id}/bia",
        headers=headers,
        json={"impact_analysis_json": {"financial": "low"}, "review_frequency_months": 12},
    )
    assert bia_resp.status_code == 201, bia_resp.text

    membership.status = "inactive"
    owner.status = "disabled"
    db_session.commit()

    overdue_resp = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_resp.status_code == 200, overdue_resp.text
    matching = [item for item in overdue_resp.json()["items"] if item["process_id"] == process_id]
    assert len(matching) == 1
    assert matching[0]["is_stale"] is True
    assert any("deactivated" in reason for reason in matching[0]["stale_reasons"])
    assert any("membership is inactive" in reason for reason in matching[0]["stale_reasons"])


def test_process_with_no_bia_appears_in_overdue_reviews(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-nobia")
    headers = org_user["org_headers"]

    resp = _create_process(client, headers)
    assert resp.status_code == 201, resp.text
    process_id = resp.json()["id"]

    overdue_resp = client.get("/api/v1/bcm/overdue-reviews", headers=headers)
    assert overdue_resp.status_code == 200, overdue_resp.text
    items = overdue_resp.json()["items"]
    matching = [item for item in items if item["process_id"] == process_id]
    assert len(matching) == 1
    assert matching[0]["is_stale"] is True
    assert matching[0]["latest_bia"] is None
    assert any("No BIA assessment" in reason for reason in matching[0]["stale_reasons"])


def test_invalid_criticality_tier_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-badtier")
    headers = org_user["org_headers"]

    resp = _create_process(client, headers, criticality_tier="not_a_real_tier")
    assert resp.status_code == 422, resp.text


def test_negative_rto_rpo_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="bcm-negrto")
    headers = org_user["org_headers"]

    resp = _create_process(client, headers, recovery_time_objective_hours=-1)
    assert resp.status_code == 422, resp.text

    resp2 = _create_process(client, headers, recovery_point_objective_hours=-5)
    assert resp2.status_code == 422, resp2.text
