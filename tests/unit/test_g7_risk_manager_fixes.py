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


def test_item2_factor_based_residual_score_uses_factor_methodology_not_plain_multiplication(client):
    """G7 item 2 regression: residual_score for a factor_based risk must use the same
    factor-based methodology as inherent_score, not the standard likelihood*impact
    multiplication.
    """
    org = bootstrap_org_user(client, email_prefix="g7-residual-factor")
    headers = org["org_headers"]

    put = client.put(
        "/api/v1/compliance/risk-settings",
        headers=headers,
        json={"financial_weight": 0.4, "brand_weight": 0.3, "operational_weight": 0.3},
    )
    assert put.status_code == 200

    created = client.post(
        "/api/v1/risks",
        headers=headers,
        json={
            "title": "Factor residual risk",
            "category": "operational",
            "likelihood": 5,
            "impact": 5,
            "composite_score_method": "factor_based",
            "financial_impact": 5,
            "brand_impact": 5,
            "operational_impact": 5,
        },
    )
    assert created.status_code == 201, created.text
    risk_id = created.json()["id"]
    inherent_score = created.json()["inherent_score"]
    assert inherent_score == 25

    control = client.post(
        "/api/v1/controls",
        headers=headers,
        json={
            "title": "Critical mitigating control",
            "control_type": "technical",
            "criticality": "critical",
        },
    )
    assert control.status_code == 201, control.text
    control_id = control.json()["id"]

    implemented = client.patch(
        f"/api/v1/controls/{control_id}",
        headers=headers,
        json={"status": "implemented"},
    )
    assert implemented.status_code == 200, implemented.text

    linked = client.post(
        f"/api/v1/risks/{risk_id}/controls",
        headers=headers,
        json={"control_id": control_id, "link_type": "mitigates"},
    )
    assert linked.status_code == 200, linked.text

    detail = client.get(f"/api/v1/risks/{risk_id}", headers=headers)
    assert detail.status_code == 200
    body = detail.json()

    # One implemented critical control reduces likelihood by 2 (5 -> 3). A plain
    # likelihood*impact residual formula would give 3*5=15. The correct factor-based
    # residual re-applies the SAME weighted factor composite (financial/brand/operational
    # are unchanged by controls) with the reduced likelihood: composite=5.0, likelihood
    # multiplier 3/3=1.0 -> raw 5.0 -> scaled 25, clamped to inherent_score=25.
    assert body["residual_likelihood"] == 3
    assert body["residual_score"] != 15, (
        "BUG: residual_score used the plain likelihood*impact formula instead of the "
        "factor-based methodology"
    )
    assert body["residual_score"] == 25
