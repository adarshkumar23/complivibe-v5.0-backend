from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

PBC_BASE = "/api/v1/compliance/pbc-items"
SCHEDULE_BASE = "/api/v1/compliance/audit-schedules"
ENGAGEMENT_BASE = "/api/v1/compliance/audit-engagements"
AI_QUESTIONS_URL = "/api/v1/ai-governance/risk-assessments/questions"


def _login(client, email: str, password: str = "Pass1234!@") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


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


# ---------------------------------------------------------------------------
# Item 1: PBC item acceptance requires evidence or a documented override
# ---------------------------------------------------------------------------


def _create_engagement(client, headers: dict[str, str], title: str = "PBC Audit") -> dict:
    payload = {
        "title": title,
        "audit_type": "internal_readiness",
        "scope_framework_ids": [],
        "assigned_auditor_ids": [],
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
        "notes": "test",
    }
    response = client.post(ENGAGEMENT_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_evidence(client, headers: dict[str, str], title: str = "Evidence") -> dict:
    payload = {
        "title": title,
        "description": "Evidence description",
        "evidence_type": "document",
        "source": "manual",
    }
    response = client.post("/api/v1/evidence", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_pbc_item(client, headers: dict[str, str], engagement_id: str, title: str = "PBC item") -> dict:
    response = client.post(
        f"{PBC_BASE}?engagement_id={engagement_id}",
        headers=headers,
        json={"title": title, "description": "desc", "due_date": (date.today() + timedelta(days=5)).isoformat()},
    )
    assert response.status_code == 201
    return response.json()


def test_pbc_accept_blocked_without_evidence_or_override(client):
    org = bootstrap_org_user(client, email_prefix="g7-pbc")
    engagement = _create_engagement(client, org["org_headers"])
    item = _create_pbc_item(client, org["org_headers"], engagement["id"])

    # Submit with no evidence attached -- this is the "missing evidence" state.
    submitted = client.post(f"{PBC_BASE}/{item['id']}/submit", headers=org["org_headers"], json={})
    assert submitted.status_code == 200
    assert submitted.json()["evidence_id"] is None

    # Root-cause check: accepting with no evidence and no override reason must be rejected.
    blocked = client.post(f"{PBC_BASE}/{item['id']}/accept", headers=org["org_headers"], json={})
    assert blocked.status_code == 422
    assert "evidence" in blocked.json()["detail"].lower()

    # An empty/whitespace-only override reason must not count as a real override.
    blocked_blank = client.post(
        f"{PBC_BASE}/{item['id']}/accept",
        headers=org["org_headers"],
        json={"override_reason": "   "},
    )
    assert blocked_blank.status_code in (400, 422)

    # A genuine, documented override reason is accepted and recorded.
    accepted = client.post(
        f"{PBC_BASE}/{item['id']}/accept",
        headers=org["org_headers"],
        json={"override_reason": "Client verbally confirmed compliance; formal evidence pending next audit cycle."},
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "accepted"
    assert body["acceptance_override_reason"] == (
        "Client verbally confirmed compliance; formal evidence pending next audit cycle."
    )


def test_pbc_accept_succeeds_with_evidence_no_override_needed(client):
    org = bootstrap_org_user(client, email_prefix="g7-pbc-ev")
    engagement = _create_engagement(client, org["org_headers"])
    evidence = _create_evidence(client, org["org_headers"])
    item = _create_pbc_item(client, org["org_headers"], engagement["id"])

    submitted = client.post(
        f"{PBC_BASE}/{item['id']}/submit",
        headers=org["org_headers"],
        json={"evidence_id": evidence["id"]},
    )
    assert submitted.status_code == 200
    assert submitted.json()["evidence_id"] == evidence["id"]

    accepted = client.post(f"{PBC_BASE}/{item['id']}/accept", headers=org["org_headers"], json={})
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["status"] == "accepted"
    assert body["acceptance_override_reason"] is None


# ---------------------------------------------------------------------------
# Item 2: manually-linked engagements must show up in schedule history
# ---------------------------------------------------------------------------


def _framework_id(client, headers: dict[str, str]) -> str:
    resp = client.get("/api/v1/frameworks", headers=headers)
    assert resp.status_code == 200
    frameworks = resp.json()
    assert frameworks
    return frameworks[0]["id"]


def _create_schedule(client, headers: dict[str, str], framework_id: str) -> dict:
    payload = {
        "title": "G7 schedule",
        "audit_type": "internal_readiness",
        "framework_id": framework_id,
        "recurrence_pattern": "annual",
        "next_audit_date": (date.today() + timedelta(days=10)).isoformat(),
    }
    resp = client.post(SCHEDULE_BASE, headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_manual_link_engagement_appears_in_schedule_history(client):
    org = bootstrap_org_user(client, email_prefix="g7-sched")
    framework_id = _framework_id(client, org["org_headers"])
    schedule = _create_schedule(client, org["org_headers"], framework_id)
    engagement = _create_engagement(client, org["org_headers"], title="Manually linked audit")

    # Before linking: engagement was created independently, no schedule attribution.
    history_before = client.get(f"{SCHEDULE_BASE}/{schedule['id']}/history", headers=org["org_headers"])
    assert history_before.status_code == 200
    assert engagement["id"] not in {row["id"] for row in history_before.json()}

    linked = client.post(
        f"{SCHEDULE_BASE}/{schedule['id']}/link-engagement",
        headers=org["org_headers"],
        json={"engagement_id": engagement["id"]},
    )
    assert linked.status_code == 200

    # Root-cause check: the manually-linked engagement must now appear in the
    # same history trail as automated ones (get_schedule_history scopes by
    # source_schedule_id, which link_engagement must now populate).
    history_after = client.get(f"{SCHEDULE_BASE}/{schedule['id']}/history", headers=org["org_headers"])
    assert history_after.status_code == 200
    history_ids = {row["id"] for row in history_after.json()}
    assert engagement["id"] in history_ids


# ---------------------------------------------------------------------------
# Item 3: AI risk assessment question discovery endpoint
# ---------------------------------------------------------------------------


def test_ai_risk_assessment_questions_discovery_endpoint(client):
    org = bootstrap_org_user(client, email_prefix="g7-ai-q")

    resp = client.get(AI_QUESTIONS_URL, headers=org["org_headers"])
    assert resp.status_code == 200
    questions = resp.json()
    assert len(questions) >= 6  # at least one per risk dimension

    dimensions = {q["risk_dimension"] for q in questions}
    assert dimensions == {"bias", "fairness", "explainability", "privacy", "misuse", "security"}
    for q in questions:
        assert q["id"]
        assert q["question_text"]
        assert q["is_active"] is True

    # The IDs discovered here must be the same ones accepted by submit-responses,
    # i.e. this endpoint is a genuine, non-decorative discovery mechanism.
    ai_system = client.post(
        "/api/v1/ai-governance/systems",
        headers=org["org_headers"],
        json={"name": "Discovery Test System", "system_type": "model", "owner_id": org["user_id"]},
    )
    assert ai_system.status_code == 201

    assessment = client.post(
        f"/api/v1/ai-governance/systems/{ai_system.json()['id']}/risk-assessments",
        headers=org["org_headers"],
    )
    assert assessment.status_code == 201

    first_question_id = questions[0]["id"]
    submit = client.post(
        f"/api/v1/ai-governance/risk-assessments/{assessment.json()['id']}/submit-responses",
        headers=org["org_headers"],
        json={"responses": [{"question_id": first_question_id, "response": "low_risk"}]},
    )
    assert submit.status_code == 200


# ---------------------------------------------------------------------------
# Item 4: reviewer role must have the real permissions needed to review
# ---------------------------------------------------------------------------


def test_reviewer_role_has_review_permissions_and_can_approve_control_exception(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer")
    org_id = org["organization_id"]

    reviewer = _create_active_user_with_role(db_session, org_id, "g7-reviewer-user@example.com", "reviewer")
    reviewer_token = _login(client, reviewer.email)

    perms = client.get("/api/v1/auth/permissions", headers=_headers(reviewer_token, org_id))
    assert perms.status_code == 200
    codes = set(perms.json()["permission_codes"])
    # Retained role/quorum approval grants (no per-assignment fallback exists):
    assert "exceptions:approve" in codes
    assert "ai_governance:approve" in codes
    assert "governance_override:approve" in codes
    # Reviewer-appropriate submit verb is kept; broader-control manage is not.
    assert "policy_exceptions:submit" in codes
    assert "policy_exceptions:manage" not in codes
    # De-scoped by migration 0306: reviewer approves a policy only via per-request
    # assignment (approver_user_id), NOT via a blanket org-wide grant.
    assert "compliance_policies:approve" not in codes

    # Concrete end-to-end proof: reviewer can actually approve a control exception,
    # which was blocked before because the role had no "exceptions:approve" grant.
    control = client.post(
        "/api/v1/controls",
        headers=org["org_headers"],
        json={
            "title": "G7 Control",
            "description": "desc",
            "control_type": "process",
            "criticality": "high",
            "owner_user_id": org["user_id"],
        },
    )
    assert control.status_code == 201

    exception = client.post(
        "/api/v1/compliance/control-exceptions",
        headers=org["org_headers"],
        json={
            "control_id": control.json()["id"],
            "title": "G7 Exception",
            "description": "desc",
            "exception_type": "temporary",
            "risk_acceptance_reason": "accepted risk",
            "owner_user_id": org["user_id"],
            "effective_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=90)).isoformat(),
        },
    )
    assert exception.status_code == 201

    approve = client.post(
        f"/api/v1/compliance/control-exceptions/{exception.json()['id']}/approve",
        headers=_headers(reviewer_token, org_id),
        json={"decision_notes": "Reviewed and approved"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] in ("approved", "active")
