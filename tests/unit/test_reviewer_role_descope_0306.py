"""Reviewer role de-scope (migration 0306_reviewer_role_descope).

Pins the corrected reviewer boundary:
  * general write to the risk register / evidence is denied (403);
  * the reviewer holds NO blanket compliance_policies:approve, so a reviewer
    who is NOT the assigned approver cannot approve a policy (403);
  * a reviewer who IS assigned as the approver on a specific request CAN still
    approve THAT request via the per-request assignment path (200) -- the
    de-scope must not break legitimate assigned-reviewer approval.
"""
from __future__ import annotations

import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

POLICIES = "/api/v1/compliance/policies"
EVIDENCE = "/api/v1/evidence"


def _user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
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
    db_session.add(Membership(organization_id=uuid.UUID(org_id), user_id=user.id, role_id=role.id, status="active"))
    db_session.commit()
    return user


def _reviewer(client, db_session, org_id: str, prefix: str):
    user = _user_with_role(db_session, org_id, f"{prefix}@example.com", "reviewer")
    return user, org_headers(login_user(client, user.email), org_id)


def test_reviewer_denied_risks_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="descope-risk")
    _, headers = _reviewer(client, db_session, org["organization_id"], "descope-risk-rev")
    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={"title": "x", "category": "operational", "likelihood": 2, "impact": 3},
    )
    assert resp.status_code == 403, resp.text
    assert "risks:write" in resp.json()["detail"]


def test_reviewer_denied_evidence_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="descope-evi")
    _, headers = _reviewer(client, db_session, org["organization_id"], "descope-evi-rev")
    resp = client.post(EVIDENCE, headers=headers, json={"title": "reviewer evidence"})
    assert resp.status_code == 403, resp.text
    assert "evidence:write" in resp.json()["detail"]


def _submitted_version(client, owner_headers, owner_id: str):
    """Create a policy + submitted version, return (policy_id, version_id)."""
    policy = client.post(
        POLICIES,
        headers=owner_headers,
        json={"title": "Descope Policy", "policy_type": "acceptable_use", "owner_user_id": owner_id},
    ).json()
    version = client.post(
        f"{POLICIES}/{policy['id']}/versions",
        headers=owner_headers,
        json={"version_number": "1.0", "content_snapshot_json": {"rev": 1}, "change_summary": "v1"},
    ).json()
    submitted = client.post(
        f"{POLICIES}/{policy['id']}/versions/{version['id']}/submit-for-approval",
        headers=owner_headers,
        json={"notes": "submit"},
    )
    assert submitted.status_code == 200, submitted.text
    return policy["id"], version["id"]


def _approval_request(client, owner_headers, policy_id: str, version_id: str, approver_user_id: str) -> dict:
    resp = client.post(
        f"{POLICIES}/{policy_id}/approval-requests",
        headers=owner_headers,
        json={"version_id": version_id, "approver_user_id": approver_user_id, "notes": "review"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_reviewer_without_assignment_cannot_approve_policy(client, db_session):
    """Reviewer holds no blanket compliance_policies:approve and is not the
    assigned approver -> approval is refused (403)."""
    org = bootstrap_org_user(client, email_prefix="descope-noassign")
    owner_headers = org["org_headers"]
    other = _user_with_role(db_session, org["organization_id"], "descope-other-approver@example.com", "admin")
    reviewer, reviewer_headers = _reviewer(client, db_session, org["organization_id"], "descope-noassign-rev")

    policy_id, version_id = _submitted_version(client, owner_headers, org["user_id"])
    req = _approval_request(client, owner_headers, policy_id, version_id, approver_user_id=str(other.id))

    denied = client.post(
        f"{POLICIES}/{policy_id}/approval-requests/{req['id']}/approve",
        headers=reviewer_headers,
        json={"notes": "not my request"},
    )
    assert denied.status_code == 403, denied.text


def test_reviewer_with_assignment_can_approve_that_policy(client, db_session):
    """The per-request assignment path still works: a reviewer named as the
    approver_user_id can approve THAT request without any blanket grant."""
    org = bootstrap_org_user(client, email_prefix="descope-assign")
    owner_headers = org["org_headers"]
    reviewer, reviewer_headers = _reviewer(client, db_session, org["organization_id"], "descope-assign-rev")

    policy_id, version_id = _submitted_version(client, owner_headers, org["user_id"])
    req = _approval_request(client, owner_headers, policy_id, version_id, approver_user_id=str(reviewer.id))

    approved = client.post(
        f"{POLICIES}/{policy_id}/approval-requests/{req['id']}/approve",
        headers=reviewer_headers,
        json={"notes": "assigned reviewer approves"},
    )
    assert approved.status_code == 200, approved.text
