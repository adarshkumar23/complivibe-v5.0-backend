"""G7 confirmed-bug fixes: Risk Manager (reviewer) permissions, factor-based
likelihood scoring, risk-to-risk dependency graph, and quantify schema.
"""
from __future__ import annotations

import uuid

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, org_headers, login_user


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
    db_session.add(
        Membership(
            organization_id=uuid.UUID(org_id),
            user_id=user.id,
            role_id=role.id,
            status="active",
        )
    )
    db_session.commit()
    return user


def _reviewer_headers(client, db_session, org_id: str, email_prefix: str):
    email = f"{email_prefix}@example.com"
    _create_active_user_with_role(db_session, org_id, email, "reviewer")
    token = login_user(client, email)
    return org_headers(token, org_id)


def test_item1_reviewer_can_create_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer-risk")
    headers = _reviewer_headers(client, db_session, org["organization_id"], "g7-reviewer-risk-user")

    resp = client.post(
        "/api/v1/risks",
        headers=headers,
        json={"title": "Reviewer-created risk", "category": "operational", "likelihood": 2, "impact": 3},
    )
    assert resp.status_code == 201, resp.text


def test_item1_reviewer_can_write_risk_indicator(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer-kri")
    headers = _reviewer_headers(client, db_session, org["organization_id"], "g7-reviewer-kri-user")

    resp = client.post(
        "/api/v1/compliance/risk-indicators",
        headers=headers,
        json={
            "name": "Reviewer KRI",
            "metric_type": "custom",
            "target_value": 10,
            "warning_threshold": 20,
            "critical_threshold": 30,
            "owner_user_id": org["user_id"],
        },
    )
    assert resp.status_code == 201, resp.text


def test_item1_reviewer_can_write_risk_appetite(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-reviewer-appetite")
    headers = _reviewer_headers(client, db_session, org["organization_id"], "g7-reviewer-appetite-user")

    resp = client.post(
        "/api/v1/compliance/risk-appetite",
        headers=headers,
        json={
            "risk_category": "operational",
            "scope_type": "org",
            "max_acceptable_score": 15,
            "escalation_owner_id": org["user_id"],
        },
    )
    assert resp.status_code == 201, resp.text
