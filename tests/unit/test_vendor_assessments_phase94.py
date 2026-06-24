import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
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


def _create_vendor(client, headers: dict[str, str], *, owner_user_id: str, name: str = "Vendor") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_assessment(client, headers: dict[str, str], vendor_id: str, *, title: str = "Initial Assessment", assigned_to_user_id: str | None = None) -> dict:
    payload = {
        "title": title,
        "assessment_type": "initial",
        "overall_rating": "not_rated",
    }
    if assigned_to_user_id is not None:
        payload["assigned_to_user_id"] = assigned_to_user_id

    response = client.post(f"{VENDORS_BASE}/{vendor_id}/assessments", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _archive_vendor(client, headers: dict[str, str], vendor_id: str) -> None:
    archived = client.post(f"{VENDORS_BASE}/{vendor_id}/archive", headers=headers, json={"reason": "retired"})
    assert archived.status_code == 200


def test_phase94_assessment_crud_and_lifecycle(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p94-crud")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p94-owner@example.com", "admin")
    assignee = _create_active_user_with_role(db_session, org["organization_id"], "p94-assignee@example.com", "admin")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Lifecycle Vendor")
    assessment = _create_assessment(
        client,
        org["org_headers"],
        vendor["id"],
        title="Lifecycle Assessment",
        assigned_to_user_id=str(assignee.id),
    )
    assert assessment["status"] == "draft"

    listed = client.get(f"{VENDORS_BASE}/{vendor['id']}/assessments", headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    started = client.post(f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/start", headers=org["org_headers"])
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"
    assert started.json()["started_at"] is not None

    to_review = client.patch(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}",
        headers=org["org_headers"],
        json={"status": "under_review", "findings_summary": "some findings"},
    )
    assert to_review.status_code == 200
    assert to_review.json()["status"] == "under_review"

    completed = client.post(f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/complete", headers=org["org_headers"])
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_at"] is not None

    cancel_after_complete = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/cancel",
        headers=org["org_headers"],
        json={"cancellation_reason": "should fail"},
    )
    assert cancel_after_complete.status_code == 400


def test_phase94_archived_vendor_blocking_and_assignee_validation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p94-arch")
    other_org = bootstrap_org_user(client, email_prefix="p94-arch-other")

    owner = _create_active_user_with_role(db_session, org["organization_id"], "p94-arch-owner@example.com", "admin")
    other_assignee = _create_active_user_with_role(db_session, other_org["organization_id"], "p94-cross-assignee@example.com", "admin")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Archived Vendor")

    bad_assignee = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments",
        headers=org["org_headers"],
        json={"title": "Bad Assignee", "assessment_type": "initial", "assigned_to_user_id": str(other_assignee.id)},
    )
    assert bad_assignee.status_code == 400
    assert "assigned_to_user_id" in bad_assignee.json()["detail"]

    _archive_vendor(client, org["org_headers"], vendor["id"])

    blocked = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments",
        headers=org["org_headers"],
        json={"title": "Should Block", "assessment_type": "initial"},
    )
    assert blocked.status_code == 400


def test_phase94_question_add_answer_update_and_blocks(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p94-qa")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p94-qa-owner@example.com", "admin")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Question Vendor")
    assessment = _create_assessment(client, org["org_headers"], vendor["id"], title="Question Assessment")

    q1 = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions",
        headers=org["org_headers"],
        json={"question_text": "Do you have SOC 2?", "question_category": "compliance", "sort_order": 0},
    )
    assert q1.status_code == 201

    q2_bad_sort = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions",
        headers=org["org_headers"],
        json={"question_text": "Invalid sort", "question_category": "other", "sort_order": -1},
    )
    assert q2_bad_sort.status_code == 422

    answer = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions/{q1.json()['id']}/answer",
        headers=org["org_headers"],
        json={"response_text": "Yes, current report available"},
    )
    assert answer.status_code == 200
    assert answer.json()["response_status"] == "answered"
    assert answer.json()["answered_at"] is not None

    update_q = client.patch(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions/{q1.json()['id']}",
        headers=org["org_headers"],
        json={"response_status": "not_applicable", "sort_order": 1},
    )
    assert update_q.status_code == 200
    assert update_q.json()["response_status"] == "not_applicable"

    start = client.post(f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/start", headers=org["org_headers"])
    assert start.status_code == 200
    cancel = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/cancel",
        headers=org["org_headers"],
        json={"cancellation_reason": "stopped"},
    )
    assert cancel.status_code == 200

    blocked_update = client.patch(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions/{q1.json()['id']}",
        headers=org["org_headers"],
        json={"question_text": "Should fail"},
    )
    assert blocked_update.status_code == 400

    blocked_answer = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions/{q1.json()['id']}/answer",
        headers=org["org_headers"],
        json={"response_text": "Should fail"},
    )
    assert blocked_answer.status_code == 400


def test_phase94_tenant_isolation_and_summary_metrics(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p94-scope1")
    org2 = bootstrap_org_user(client, email_prefix="p94-scope2")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "p94-scope-owner1@example.com", "admin")
    owner2 = _create_active_user_with_role(db_session, org2["organization_id"], "p94-scope-owner2@example.com", "admin")

    vendor1 = _create_vendor(client, org1["org_headers"], owner_user_id=str(owner1.id), name="Scoped Vendor 1")
    _create_vendor(client, org2["org_headers"], owner_user_id=str(owner2.id), name="Scoped Vendor 2")

    a1 = _create_assessment(client, org1["org_headers"], vendor1["id"], title="A1")
    a2 = _create_assessment(client, org1["org_headers"], vendor1["id"], title="A2")

    start = client.post(f"{VENDORS_BASE}/{vendor1['id']}/assessments/{a1['id']}/start", headers=org1["org_headers"])
    assert start.status_code == 200
    complete = client.post(f"{VENDORS_BASE}/{vendor1['id']}/assessments/{a1['id']}/complete", headers=org1["org_headers"])
    assert complete.status_code == 200

    cancel = client.post(
        f"{VENDORS_BASE}/{vendor1['id']}/assessments/{a2['id']}/cancel",
        headers=org1["org_headers"],
        json={"cancellation_reason": "cancelled"},
    )
    assert cancel.status_code == 200

    cross_detail = client.get(
        f"{VENDORS_BASE}/{vendor1['id']}/assessments/{a1['id']}",
        headers=org2["org_headers"],
    )
    assert cross_detail.status_code == 404

    summary = client.get(f"{VENDORS_BASE}/{vendor1['id']}/assessments/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_assessments"] == 2
    assert body["completed_assessments"] == 1
    assert body["cancelled_assessments"] == 1
    assert body["active_assessments"] == 0
    assert body["by_status"]["completed"] == 1
    assert body["by_status"]["cancelled"] == 1


def test_phase94_audit_events(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p94-audit")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "p94-audit-owner@example.com", "admin")

    vendor = _create_vendor(client, org["org_headers"], owner_user_id=str(owner.id), name="Audit Vendor")
    assessment = _create_assessment(client, org["org_headers"], vendor["id"], title="Audit Assessment")

    q = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions",
        headers=org["org_headers"],
        json={"question_text": "Question?", "question_category": "security", "sort_order": 0},
    )
    assert q.status_code == 201

    started = client.post(f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/start", headers=org["org_headers"])
    assert started.status_code == 200

    answered = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/questions/{q.json()['id']}/answer",
        headers=org["org_headers"],
        json={"response_text": "Answer"},
    )
    assert answered.status_code == 200

    completed = client.post(f"{VENDORS_BASE}/{vendor['id']}/assessments/{assessment['id']}/complete", headers=org["org_headers"])
    assert completed.status_code == 200

    # second assessment for cancel audit
    second = _create_assessment(client, org["org_headers"], vendor["id"], title="Cancel Assessment")
    cancelled = client.post(
        f"{VENDORS_BASE}/{vendor['id']}/assessments/{second['id']}/cancel",
        headers=org["org_headers"],
        json={"cancellation_reason": "cancel for audit"},
    )
    assert cancelled.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "vendor_assessment.created" in actions
    assert "vendor_assessment.started" in actions
    assert "vendor_assessment.completed" in actions
    assert "vendor_assessment.cancelled" in actions
    assert "vendor_assessment_question.answered" in actions
