from datetime import date, timedelta
import uuid

from app.compliance.services.policy_exception_service import PolicyExceptionService
from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.policy_exception import PolicyException
from app.models.policy_exception_approval import PolicyExceptionApproval
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/policy-exceptions"


def _create_active_user_with_role(db_session, org_id: str, email: str, role_name: str = "reviewer") -> User:
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


def _create_policy(client, headers: dict[str, str], *, owner_user_id: str, title: str, version: str = "1.0") -> dict:
    response = client.post(
        "/api/v1/compliance/policies",
        headers=headers,
        json={
            "title": title,
            "description": "Policy text",
            "policy_type": "access_control",
            "status": "draft",
            "owner_user_id": owner_user_id,
            "version": version,
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_exception(
    client,
    headers: dict[str, str],
    *,
    policy_id: str,
    title: str = "Policy exception",
    requested_expiry: date | None = None,
    risk_level: str = "medium",
) -> dict:
    response = client.post(
        BASE,
        headers=headers,
        json={
            "policy_id": policy_id,
            "policy_version": "1.0",
            "title": title,
            "description": "Need temporary policy deviation",
            "justification": "Business requirement",
            "compensating_measure": "Manual oversight",
            "requestor_scope": "team:infra",
            "requested_expiry_date": (requested_expiry or (date.today() + timedelta(days=30))).isoformat(),
            "risk_level": risk_level,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_a32_exception_lifecycle_create_update_list_withdraw(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a32-life")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="A3.2 Policy")

    created = _create_exception(client, org["org_headers"], policy_id=policy["id"], risk_level="high")
    assert created["status"] == "pending"
    assert created["policy"]["id"] == policy["id"]

    listed = client.get(BASE, headers=org["org_headers"], params={"status": "pending", "risk_level": "high"})
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    updated = client.patch(
        f"{BASE}/{created['id']}",
        headers=org["org_headers"],
        json={"title": "Updated title", "requested_expiry_date": (date.today() + timedelta(days=45)).isoformat()},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated title"

    withdrawn = client.delete(f"{BASE}/{created['id']}", headers=org["org_headers"])
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"

    hidden = client.get(BASE, headers=org["org_headers"])
    assert hidden.status_code == 200
    assert hidden.json() == []

    row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(created["id"])).one()
    assert row.status == "withdrawn"
    assert row.deleted_at is not None


def test_a32_policy_cross_org_forbidden_and_tenant_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a32-org-a")
    org_b = bootstrap_org_user(client, email_prefix="a32-org-b")
    policy_b = _create_policy(client, org_b["org_headers"], owner_user_id=org_b["user_id"], title="B Policy")

    cross_policy = client.post(
        BASE,
        headers=org_a["org_headers"],
        json={
            "policy_id": policy_b["id"],
            "policy_version": "1.0",
            "title": "bad",
            "description": "bad",
            "justification": "bad",
            "requested_expiry_date": (date.today() + timedelta(days=5)).isoformat(),
            "risk_level": "low",
        },
    )
    assert cross_policy.status_code in {403, 404}

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="A Policy")
    exception_a = _create_exception(client, org_a["org_headers"], policy_id=policy_a["id"])

    cannot_see = client.get(f"{BASE}/{exception_a['id']}", headers=org_b["org_headers"])
    assert cannot_see.status_code == 404


def test_a32_approval_rejection_flow_and_immutability(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a32-approve")
    reviewer = _create_active_user_with_role(db_session, org["organization_id"], "a32-r@example.com", role_name="reviewer")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Approval Policy")

    pending = _create_exception(client, org["org_headers"], policy_id=policy["id"])

    reviewer_headers = org_headers(login_user(client, reviewer.email), org["organization_id"])
    non_manager = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=reviewer_headers,
        json={
            "decision_reason": "ok",
            "approved_expiry_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    assert non_manager.status_code == 403

    missing_reason = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=org["org_headers"],
        json={"approved_expiry_date": (date.today() + timedelta(days=10)).isoformat()},
    )
    assert missing_reason.status_code == 422

    approved = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=org["org_headers"],
        json={
            "decision_reason": "Approved with controls",
            "approved_expiry_date": (date.today() + timedelta(days=30)).isoformat(),
            "conditions": "weekly review",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    second_approve = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=org["org_headers"],
        json={
            "decision_reason": "again",
            "approved_expiry_date": (date.today() + timedelta(days=40)).isoformat(),
        },
    )
    assert second_approve.status_code == 400

    approval = db_session.query(PolicyExceptionApproval).filter(PolicyExceptionApproval.exception_id == uuid.UUID(pending["id"])).one()
    assert approval.decision == "approved"
    assert approval.decision_reason == "Approved with controls"
    assert approval.conditions == "weekly review"

    reject_after_approve = client.post(
        f"{BASE}/{pending['id']}/reject",
        headers=org["org_headers"],
        json={"decision_reason": "should fail"},
    )
    assert reject_after_approve.status_code == 400

    pending_reject = _create_exception(client, org["org_headers"], policy_id=policy["id"], title="reject me")
    rejected = client.post(
        f"{BASE}/{pending_reject['id']}/reject",
        headers=org["org_headers"],
        json={"decision_reason": "Not acceptable"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    reject_again = client.post(
        f"{BASE}/{pending_reject['id']}/reject",
        headers=org["org_headers"],
        json={"decision_reason": "again"},
    )
    assert reject_again.status_code == 400


def test_a32_update_and_withdraw_not_allowed_after_approval(client):
    org = bootstrap_org_user(client, email_prefix="a32-state")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="State Policy")

    pending = _create_exception(client, org["org_headers"], policy_id=policy["id"])
    approved = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=org["org_headers"],
        json={
            "decision_reason": "good",
            "approved_expiry_date": (date.today() + timedelta(days=15)).isoformat(),
        },
    )
    assert approved.status_code == 200

    update_approved = client.patch(
        f"{BASE}/{pending['id']}",
        headers=org["org_headers"],
        json={"title": "cannot"},
    )
    assert update_approved.status_code == 400

    withdraw_approved = client.delete(f"{BASE}/{pending['id']}", headers=org["org_headers"])
    assert withdraw_approved.status_code == 400


def test_a32_expiry_sweep_and_org_scoping(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="a32-exp-a")
    org_b = bootstrap_org_user(client, email_prefix="a32-exp-b")

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Policy A")
    policy_b = _create_policy(client, org_b["org_headers"], owner_user_id=org_b["user_id"], title="Policy B")

    past = _create_exception(client, org_a["org_headers"], policy_id=policy_a["id"], title="past")
    future = _create_exception(client, org_a["org_headers"], policy_id=policy_a["id"], title="future")
    other_org = _create_exception(client, org_b["org_headers"], policy_id=policy_b["id"], title="other")

    client.post(
        f"{BASE}/{past['id']}/approve",
        headers=org_a["org_headers"],
        json={"decision_reason": "ok", "approved_expiry_date": (date.today() - timedelta(days=1)).isoformat()},
    )
    client.post(
        f"{BASE}/{future['id']}/approve",
        headers=org_a["org_headers"],
        json={"decision_reason": "ok", "approved_expiry_date": (date.today() + timedelta(days=10)).isoformat()},
    )
    client.post(
        f"{BASE}/{other_org['id']}/approve",
        headers=org_b["org_headers"],
        json={"decision_reason": "ok", "approved_expiry_date": (date.today() - timedelta(days=1)).isoformat()},
    )

    expired_count = PolicyExceptionService(db_session).expire_exceptions(uuid.UUID(org_a["organization_id"]))
    db_session.commit()
    assert expired_count == 1

    past_row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(past["id"])).one()
    future_row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(future["id"])).one()
    other_row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(other_org["id"])).one()
    assert past_row.status == "expired"
    assert future_row.status == "approved"
    assert other_row.status == "approved"

    cannot_approve_expired = client.post(
        f"{BASE}/{past['id']}/approve",
        headers=org_a["org_headers"],
        json={"decision_reason": "no", "approved_expiry_date": (date.today() + timedelta(days=3)).isoformat()},
    )
    assert cannot_approve_expired.status_code == 400


def test_a32_dashboard_and_policy_summary_metrics(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a32-metrics")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Metrics Policy")

    pending_overdue = _create_exception(
        client,
        org["org_headers"],
        policy_id=policy["id"],
        title="overdue-pending",
        requested_expiry=date.today() - timedelta(days=1),
        risk_level="medium",
    )
    _ = pending_overdue
    expiring = _create_exception(client, org["org_headers"], policy_id=policy["id"], title="expiring", risk_level="high")
    long_active = _create_exception(client, org["org_headers"], policy_id=policy["id"], title="long", risk_level="critical")

    approve_expiring = client.post(
        f"{BASE}/{expiring['id']}/approve",
        headers=org["org_headers"],
        json={
            "decision_reason": "ok",
            "approved_expiry_date": (date.today() + timedelta(days=7)).isoformat(),
            "conditions": "monitor",
        },
    )
    assert approve_expiring.status_code == 200

    approve_long = client.post(
        f"{BASE}/{long_active['id']}/approve",
        headers=org["org_headers"],
        json={"decision_reason": "ok", "approved_expiry_date": (date.today() + timedelta(days=60)).isoformat()},
    )
    assert approve_long.status_code == 200

    second_policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Summary Policy 2")
    second = _create_exception(client, org["org_headers"], policy_id=second_policy["id"], title="other")
    rejected = client.post(
        f"{BASE}/{second['id']}/reject",
        headers=org["org_headers"],
        json={"decision_reason": "reject"},
    )
    assert rejected.status_code == 200

    dashboard = client.get(f"{BASE}/dashboard", headers=org["org_headers"])
    assert dashboard.status_code == 200
    body = dashboard.json()
    assert body["total_pending"] == 1
    assert body["total_active"] == 2
    assert len(body["expiring_soon"]) == 1
    assert body["expiring_soon"][0]["id"] == expiring["id"]
    assert {item["id"] for item in body["high_risk_active"]} == {expiring["id"], long_active["id"]}
    assert len(body["overdue_pending"]) == 1

    summary_policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Summary Duration Policy")
    duration_30 = _create_exception(client, org["org_headers"], policy_id=summary_policy["id"], title="d30")
    duration_60 = _create_exception(client, org["org_headers"], policy_id=summary_policy["id"], title="d60")
    approve_30 = client.post(
        f"{BASE}/{duration_30['id']}/approve",
        headers=org["org_headers"],
        json={"decision_reason": "ok", "approved_expiry_date": (date.today() + timedelta(days=30)).isoformat()},
    )
    assert approve_30.status_code == 200
    approve_60 = client.post(
        f"{BASE}/{duration_60['id']}/approve",
        headers=org["org_headers"],
        json={"decision_reason": "ok", "approved_expiry_date": (date.today() + timedelta(days=60)).isoformat()},
    )
    assert approve_60.status_code == 200

    summary = client.get(f"/api/v1/compliance/policies/{summary_policy['id']}/exception-summary", headers=org["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["active_exceptions"] == 2
    assert summary_body["pending_count"] == 0
    assert summary_body["historical_count"] == 0
    assert abs(float(summary_body["avg_exception_duration_days"]) - 45.0) < 0.01


def test_a32_tenant_isolation_for_approval(client):
    org_a = bootstrap_org_user(client, email_prefix="a32-tenant-a")
    org_b = bootstrap_org_user(client, email_prefix="a32-tenant-b")

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Tenant A")
    exception_a = _create_exception(client, org_a["org_headers"], policy_id=policy_a["id"])

    approve_cross = client.post(
        f"{BASE}/{exception_a['id']}/approve",
        headers=org_b["org_headers"],
        json={"decision_reason": "cross", "approved_expiry_date": (date.today() + timedelta(days=5)).isoformat()},
    )
    assert approve_cross.status_code == 404
