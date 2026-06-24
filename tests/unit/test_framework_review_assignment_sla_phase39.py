import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.email_outbox import EmailOutbox
from app.models.framework_review_escalation_event import FrameworkReviewEscalationEvent
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _login(client, email: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _org_id(client, token: str) -> str:
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def _framework_id_by_code(client, token: str, code: str) -> str:
    response = client.get("/api/v1/frameworks", headers=_headers(token))
    assert response.status_code == 200
    for item in response.json():
        if item["code"] == code:
            return item["id"]
    raise AssertionError(f"Framework {code} not found")


def _apply_starter_pack(client, token: str, org_id: str, pack_key: str = "eu_ai_act_starter") -> None:
    response = client.post(
        f"/api/v1/framework-content/packs/{pack_key}/apply",
        headers=_headers(token, org_id),
        json={"dry_run": False, "force_update": False},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def _persist_coverage_report(client, token: str, org_id: str, framework_id: str) -> str:
    response = client.post(
        f"/api/v1/frameworks/{framework_id}/coverage-report",
        headers=_headers(token, org_id),
        json={"persist": True},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _start_and_complete_review(client, token: str, org_id: str, framework_id: str, coverage_report_id: str) -> str:
    started = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews",
        headers=_headers(token, org_id),
        json={
            "review_type": "internal_review",
            "target_coverage_level": "starter",
            "coverage_report_id": coverage_report_id,
            "checklist_json": {"items": [{"key": "coverage", "done": True}]},
        },
    )
    assert started.status_code == 201
    review_id = started.json()["id"]

    completed = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/complete",
        headers=_headers(token, org_id),
        json={
            "outcome": "pass",
            "checklist_json": {"items": [{"key": "all", "done": True}]},
            "findings_json": {"notes": "ready"},
        },
    )
    assert completed.status_code == 200
    return review_id


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str, password: str = "Pass1234!@") -> User:
    user = User(
        email=email,
        full_name=email.split("@")[0],
        hashed_password=get_password_hash(password),
        status="active",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    db_session.flush()
    role = db_session.query(Role).filter(Role.organization_id == uuid.UUID(org_id), Role.name == role_name).one()
    membership = Membership(
        organization_id=uuid.UUID(org_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()
    return user


def test_phase39_assignment_and_queue_tenant_scoping(client, db_session):
    owner1 = _register(client, "p39-owner1@example.com", "Pass1234!@", "P39 Org1")
    org1 = _org_id(client, owner1)
    owner2 = _register(client, "p39-owner2@example.com", "Pass1234!@", "P39 Org2")
    org2 = _org_id(client, owner2)
    framework_id = _framework_id_by_code(client, owner1, "EU_AI_ACT")
    _apply_starter_pack(client, owner1, org1)
    coverage_report_id = _persist_coverage_report(client, owner1, org1, framework_id)
    review_id = _start_and_complete_review(client, owner1, org1, framework_id, coverage_report_id)

    outsider = _create_active_user_with_role(db_session, org2, "p39-outsider@example.com", "reviewer")
    outsider_assign = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=_headers(owner1, org1),
        json={"assigned_to_user_id": str(outsider.id)},
    )
    assert outsider_assign.status_code == 400

    reviewer = _create_active_user_with_role(db_session, org1, "p39-reviewer1@example.com", "reviewer")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")
    assign = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=_headers(owner1, org1),
        json={"assigned_to_user_id": str(reviewer.id), "notify": False},
    )
    assert assign.status_code == 201

    my_queue = client.get("/api/v1/framework-review-queue/my", headers=_headers(reviewer_token, org1))
    assert my_queue.status_code == 200
    assert len(my_queue.json()) == 1
    assert my_queue.json()[0]["assignment"]["assigned_to_user_id"] == str(reviewer.id)

    org_queue = client.get("/api/v1/framework-review-queue", headers=_headers(owner1, org1))
    assert org_queue.status_code == 200
    assert len(org_queue.json()) == 1

    cross_org_queue = client.get("/api/v1/framework-review-queue", headers=_headers(owner2, org2))
    assert cross_org_queue.status_code == 200
    assert cross_org_queue.json() == []


def test_phase39_assignment_accept_complete_cancel_and_audit(client, db_session):
    owner = _register(client, "p39-owner3@example.com", "Pass1234!@", "P39 Org3")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    reviewer = _create_active_user_with_role(db_session, org, "p39-reviewer2@example.com", "reviewer")
    reviewer_token = _login(client, reviewer.email, "Pass1234!@")

    assign = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=_headers(owner, org),
        json={"assigned_to_user_id": str(reviewer.id)},
    )
    assert assign.status_code == 201
    assignment_id = assign.json()["id"]

    accepted = client.post(
        f"/api/v1/framework-review-assignments/{assignment_id}/accept",
        headers=_headers(reviewer_token, org),
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    completed = client.post(
        f"/api/v1/framework-review-assignments/{assignment_id}/complete",
        headers=_headers(reviewer_token, org),
        json={"notes": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"

    assign2 = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=_headers(owner, org),
        json={"assigned_to_user_id": str(reviewer.id)},
    )
    assert assign2.status_code == 201
    assignment2_id = assign2.json()["id"]

    cancel_empty = client.post(
        f"/api/v1/framework-review-assignments/{assignment2_id}/cancel",
        headers=_headers(owner, org),
        json={"reason": ""},
    )
    assert cancel_empty.status_code == 400

    cancelled = client.post(
        f"/api/v1/framework-review-assignments/{assignment2_id}/cancel",
        headers=_headers(owner, org),
        json={"reason": "reassigning"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_pack_review.assignment_created" in actions
    assert "framework_pack_review.assignment_accepted" in actions
    assert "framework_pack_review.assignment_completed" in actions
    assert "framework_pack_review.assignment_cancelled" in actions


def test_phase39_sla_policy_crud_validation_and_evaluation(client, db_session):
    owner = _register(client, "p39-owner4@example.com", "Pass1234!@", "P39 Org4")
    org = _org_id(client, owner)
    framework_id = _framework_id_by_code(client, owner, "EU_AI_ACT")
    _apply_starter_pack(client, owner, org)
    coverage_report_id = _persist_coverage_report(client, owner, org, framework_id)
    review_id = _start_and_complete_review(client, owner, org, framework_id, coverage_report_id)

    reviewer = _create_active_user_with_role(db_session, org, "p39-reviewer3@example.com", "reviewer")
    assign = client.post(
        f"/api/v1/frameworks/{framework_id}/pack-reviews/{review_id}/assignments",
        headers=_headers(owner, org),
        json={
            "assigned_to_user_id": str(reviewer.id),
            "due_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "notify": False,
        },
    )
    assert assign.status_code == 201

    invalid_policy = client.post(
        "/api/v1/framework-review-sla-policies",
        headers=_headers(owner, org),
        json={
            "name": "invalid",
            "review_type": "internal_review",
            "due_days": -1,
            "escalation_after_days": 1,
            "reminder_before_days": 1,
            "status": "active",
        },
    )
    assert invalid_policy.status_code == 400

    created_policy = client.post(
        "/api/v1/framework-review-sla-policies",
        headers=_headers(owner, org),
        json={
            "name": "Default Review SLA",
            "review_type": "internal_review",
            "target_coverage_level": "starter",
            "due_days": 2,
            "escalation_after_days": 1,
            "reminder_before_days": 2,
            "status": "active",
        },
    )
    assert created_policy.status_code == 201
    policy_id = created_policy.json()["id"]

    updated = client.patch(
        f"/api/v1/framework-review-sla-policies/{policy_id}",
        headers=_headers(owner, org),
        json={"status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    reactivated = client.patch(
        f"/api/v1/framework-review-sla-policies/{policy_id}",
        headers=_headers(owner, org),
        json={"status": "active"},
    )
    assert reactivated.status_code == 200

    dry_run = client.post(
        "/api/v1/framework-review-queue/evaluate-sla",
        headers=_headers(owner, org),
        json={"dry_run": True, "notify": True},
    )
    assert dry_run.status_code == 200
    assert dry_run.json()["dry_run"] is True
    assert dry_run.json()["created_count"] == 0
    assert dry_run.json()["would_create_count"] >= 1
    assert db_session.query(FrameworkReviewEscalationEvent).filter_by(organization_id=uuid.UUID(org)).count() == 0

    live = client.post(
        "/api/v1/framework-review-queue/evaluate-sla",
        headers=_headers(owner, org),
        json={"dry_run": False, "notify": True},
    )
    assert live.status_code == 200
    assert live.json()["dry_run"] is False
    assert live.json()["created_count"] >= 1
    assert live.json()["queued_email_count"] >= 1

    outbox_rows = db_session.query(EmailOutbox).filter(EmailOutbox.organization_id == uuid.UUID(org)).all()
    assert len(outbox_rows) >= 1
    assert all(row.sent_at is None for row in outbox_rows)

    escalations = client.get("/api/v1/framework-review-escalations", headers=_headers(owner, org))
    assert escalations.status_code == 200
    assert len(escalations.json()) >= 1
    event_id = escalations.json()[0]["id"]

    resolved = client.post(
        f"/api/v1/framework-review-escalations/{event_id}/resolve",
        headers=_headers(owner, org),
        json={"resolution_notes": "triaged"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"

    archived = client.post(
        f"/api/v1/framework-review-sla-policies/{policy_id}/archive",
        headers=_headers(owner, org),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary = client.get("/api/v1/framework-review-queue/summary", headers=_headers(owner, org))
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_assignments"] >= 1
    assert payload["open_escalations"] >= 0

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.organization_id == uuid.UUID(org)).all()}
    assert "framework_review_sla_policy.created" in actions
    assert "framework_review_sla_policy.updated" in actions
    assert "framework_review_sla_policy.archived" in actions
    assert "framework_review_sla.evaluated" in actions
    assert "framework_review_escalation.resolved" in actions
