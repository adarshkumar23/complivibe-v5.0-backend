from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
ORG_GUARDRAILS_BASE = "/api/v1/ai-governance/guardrails"
APPROVAL_BASE = "/api/v1/ai-governance/approval-envelopes"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str, risk_tier: str = "limited") -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": risk_tier,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "admin") -> User:
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


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def test_a64_guardrails_builtin_engine(client):
    org = bootstrap_org_user(client, email_prefix="a64-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="A64 System")

    # Create financial_limit guardrail.
    financial = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails",
        headers=org["org_headers"],
        json={
            "guardrail_type": "financial_limit",
            "constraint_description": "Limit value to 10k",
            "constraint_value": {"max_usd": 10000},
            "violation_action": "block_and_alert",
        },
    )
    assert financial.status_code == 201
    financial_id = financial.json()["id"]

    # amount > max -> blocked.
    blocked = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={
            "action_context": {
                "action_type": "financial_transaction",
                "estimated_value": 50000,
                "jurisdiction": "US",
                "user_role": "operator",
            }
        },
    )
    assert blocked.status_code == 200
    assert blocked.json()["blocked"] is True
    assert any("exceeds limit" in msg for msg in blocked.json()["violations"])

    # amount <= max -> permit.
    permitted = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={
            "action_context": {
                "action_type": "financial_transaction",
                "estimated_value": 5000,
                "jurisdiction": "US",
                "user_role": "operator",
            }
        },
    )
    assert permitted.status_code == 200
    assert permitted.json()["decision"] == "permit"

    # geographic scope violation -> blocked.
    geo = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails",
        headers=org["org_headers"],
        json={
            "guardrail_type": "geographic_scope",
            "constraint_description": "US/IN only",
            "constraint_value": {"allowed_regions": ["IN", "US"]},
            "violation_action": "block_and_alert",
        },
    )
    assert geo.status_code == 201

    geo_blocked = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={
            "action_context": {
                "action_type": "financial_transaction",
                "estimated_value": 100,
                "jurisdiction": "FR",
                "user_role": "operator",
            }
        },
    )
    assert geo_blocked.status_code == 200
    assert geo_blocked.json()["blocked"] is True

    # alert_only does not block.
    alert_only = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails",
        headers=org["org_headers"],
        json={
            "guardrail_type": "action_scope",
            "constraint_description": "No deletes",
            "constraint_value": {"prohibited_actions": ["delete"]},
            "violation_action": "alert_only",
        },
    )
    assert alert_only.status_code == 201

    alert_check = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={
            "action_context": {
                "action_type": "delete",
                "estimated_value": 0,
                "jurisdiction": "US",
                "user_role": "operator",
            }
        },
    )
    assert alert_check.status_code == 200
    assert alert_check.json()["blocked"] is False
    assert len(alert_check.json()["violations"]) >= 1

    # event rows are append-only for each check and each checked guardrail.
    events = client.get(f"{ORG_GUARDRAILS_BASE}/events?system_id={system_id}", headers=org["org_headers"])
    assert events.status_code == 200
    assert len(events.json()) >= 4  # at least one event per check call

    # Deactivate financial guardrail then financial check should no longer block.
    deactivated = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails/{financial_id}/deactivate",
        headers=org["org_headers"],
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    post_deactivate = client.post(
        f"{SYSTEMS_BASE}/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={
            "action_context": {
                "action_type": "financial_transaction",
                "estimated_value": 50000,
                "jurisdiction": "US",
                "user_role": "operator",
            }
        },
    )
    assert post_deactivate.status_code == 200
    # may still be blocked by other active guardrails depending on context,
    # but financial-limit reason should be gone after deactivation.
    assert not any("exceeds limit" in msg for msg in post_deactivate.json()["violations"])

    # Ensure no banned dependencies mentioned in guardrail service source.
    source = Path("app/ai_governance/services/guardrail_service.py").read_text(encoding="utf-8").lower()
    assert "httpx" not in source
    assert "opa" not in source


def test_a65_approval_envelopes(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a65-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="A65 System", risk_tier="high")

    approver1 = _create_active_user_with_role(db_session, org["organization_id"], "a65-approver1@example.com", role_name="admin")
    approver2 = _create_active_user_with_role(db_session, org["organization_id"], "a65-approver2@example.com", role_name="admin")
    non_required = _create_active_user_with_role(db_session, org["organization_id"], "a65-other@example.com", role_name="admin")

    token1 = login_user(client, approver1.email)
    token2 = login_user(client, approver2.email)
    token_other = login_user(client, non_required.email)
    headers1 = org_headers(token1, org["organization_id"])
    headers2 = org_headers(token2, org["organization_id"])
    headers_other = org_headers(token_other, org["organization_id"])

    # high-risk production with 1 approver -> 422
    too_few = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "production",
            "required_approvers": [str(approver1.id)],
            "conditions": [],
        },
    )
    assert too_few.status_code == 422

    # high-risk production with 2 approvers -> success
    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "development",
            "transition_to": "production",
            "required_approvers": [str(approver1.id), str(approver2.id)],
            "conditions": ["Security review completed"],
        },
    )
    assert created.status_code == 201
    envelope_id = created.json()["id"]

    # expires_at ~= now + 30 days
    expires_at = _parse_dt(created.json()["expires_at"])
    now = datetime.now(UTC).replace(tzinfo=None)
    assert now + timedelta(days=29, hours=23) <= expires_at <= now + timedelta(days=30, minutes=2)

    # non-required approver cannot approve
    not_allowed = client.post(
        f"{APPROVAL_BASE}/{envelope_id}/approve",
        headers=headers_other,
        json={"notes": "trying"},
    )
    assert not_allowed.status_code == 422

    # approver 1 approve -> still pending
    vote1 = client.post(
        f"{APPROVAL_BASE}/{envelope_id}/approve",
        headers=headers1,
        json={"notes": "approve 1"},
    )
    assert vote1.status_code == 200
    assert vote1.json()["status"] == "pending"

    # double-vote blocked
    double_vote = client.post(
        f"{APPROVAL_BASE}/{envelope_id}/approve",
        headers=headers1,
        json={"notes": "approve again"},
    )
    assert double_vote.status_code == 422

    # approver 2 approve -> approved + system deployment_status transition
    vote2 = client.post(
        f"{APPROVAL_BASE}/{envelope_id}/approve",
        headers=headers2,
        json={"notes": "approve 2"},
    )
    assert vote2.status_code == 200
    assert vote2.json()["status"] == "approved"

    system = client.get(f"{SYSTEMS_BASE}/{system_id}", headers=org["org_headers"])
    assert system.status_code == 200
    assert system.json()["deployment_status"] == "production"

    # Reject by any approver -> immediate rejected.
    reject_env = client.post(
        f"{SYSTEMS_BASE}/{system_id}/approval-envelopes",
        headers=org["org_headers"],
        json={
            "transition_from": "production",
            "transition_to": "staging",
            "required_approvers": [str(approver1.id), str(approver2.id)],
            "conditions": [],
        },
    )
    assert reject_env.status_code == 201

    rejected = client.post(
        f"{APPROVAL_BASE}/{reject_env.json()['id']}/reject",
        headers=headers1,
        json={"notes": "rejecting"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    # Org isolation
    org_b = bootstrap_org_user(client, email_prefix="a65-org-b")
    forbidden = client.get(f"{APPROVAL_BASE}/{envelope_id}", headers=org_b["org_headers"])
    assert forbidden.status_code == 404
