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
            "reason": f"{title}: Business requirement",
            "compensating_measure_description": "Manual oversight",
        },
    )
    assert response.status_code in {200, 201}
    return response.json()


def test_a32_exception_lifecycle_create_update_list_withdraw(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a32-life")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="A3.2 Policy")

    created = _create_exception(client, org["org_headers"], policy_id=policy["id"], risk_level="high")
    assert created["status"] == "pending"
    assert created["policy_id"] == policy["id"]

    listed = client.get(BASE, headers=org["org_headers"], params={"status_value": "pending"})
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
            "reason": "bad",
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
    approver = _create_active_user_with_role(db_session, org["organization_id"], "a32-admin@example.com", role_name="admin")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Approval Policy")

    pending = _create_exception(client, org["org_headers"], policy_id=policy["id"])

    reviewer_headers = org_headers(login_user(client, reviewer.email), org["organization_id"])
    non_manager = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=reviewer_headers,
        json={"expiry_date": (date.today() + timedelta(days=10)).isoformat()},
    )
    assert non_manager.status_code == 403

    missing_expiry = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=org["org_headers"],
        json={},
    )
    assert missing_expiry.status_code == 422

    approver_headers = org_headers(login_user(client, approver.email), org["organization_id"])
    approved = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=30)).isoformat()},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    second_approve = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=40)).isoformat()},
    )
    assert second_approve.status_code == 400

    approved_row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(pending["id"])).one()
    assert approved_row.status == "approved"
    assert approved_row.approved_by is not None

    reject_after_approve = client.post(
        f"{BASE}/{pending['id']}/reject",
        headers=org["org_headers"],
    )
    assert reject_after_approve.status_code == 400

    pending_reject = _create_exception(client, org["org_headers"], policy_id=policy["id"], title="reject me")
    rejected = client.post(
        f"{BASE}/{pending_reject['id']}/reject",
        headers=approver_headers,
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    reject_again = client.post(
        f"{BASE}/{pending_reject['id']}/reject",
        headers=approver_headers,
    )
    assert reject_again.status_code == 400


def test_a32_update_and_withdraw_not_allowed_after_approval(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a32-state")
    approver = _create_active_user_with_role(
        db_session, org["organization_id"], f"a32-state-admin-{uuid.uuid4().hex[:6]}@example.com", role_name="admin"
    )
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="State Policy")
    approver_headers = org_headers(login_user(client, approver.email), org["organization_id"])

    pending = _create_exception(client, org["org_headers"], policy_id=policy["id"])
    approved = client.post(
        f"{BASE}/{pending['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=15)).isoformat()},
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
    approver_a = _create_active_user_with_role(db_session, org_a["organization_id"], "a32-exp-admin-a@example.com", role_name="admin")
    approver_b = _create_active_user_with_role(db_session, org_b["organization_id"], "a32-exp-admin-b@example.com", role_name="admin")

    policy_a = _create_policy(client, org_a["org_headers"], owner_user_id=org_a["user_id"], title="Policy A")
    policy_b = _create_policy(client, org_b["org_headers"], owner_user_id=org_b["user_id"], title="Policy B")

    past = _create_exception(client, org_a["org_headers"], policy_id=policy_a["id"], title="past")
    future = _create_exception(client, org_a["org_headers"], policy_id=policy_a["id"], title="future")
    other_org = _create_exception(client, org_b["org_headers"], policy_id=policy_b["id"], title="other")

    client.post(
        f"{BASE}/{past['id']}/approve",
        headers=org_headers(login_user(client, approver_a.email), org_a["organization_id"]),
        json={"expiry_date": (date.today() - timedelta(days=1)).isoformat()},
    )
    client.post(
        f"{BASE}/{future['id']}/approve",
        headers=org_headers(login_user(client, approver_a.email), org_a["organization_id"]),
        json={"expiry_date": (date.today() + timedelta(days=10)).isoformat()},
    )
    client.post(
        f"{BASE}/{other_org['id']}/approve",
        headers=org_headers(login_user(client, approver_b.email), org_b["organization_id"]),
        json={"expiry_date": (date.today() - timedelta(days=1)).isoformat()},
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
        json={"expiry_date": (date.today() + timedelta(days=3)).isoformat()},
    )
    assert cannot_approve_expired.status_code == 400


def test_a32_dashboard_and_policy_summary_metrics(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a32-metrics")
    approver = _create_active_user_with_role(db_session, org["organization_id"], "a32-metrics-admin@example.com", role_name="admin")
    approver_headers = org_headers(login_user(client, approver.email), org["organization_id"])
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
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=7)).isoformat()},
    )
    assert approve_expiring.status_code == 200

    approve_long = client.post(
        f"{BASE}/{long_active['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=60)).isoformat()},
    )
    assert approve_long.status_code == 200

    second_policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Summary Policy 2")
    second = _create_exception(client, org["org_headers"], policy_id=second_policy["id"], title="other")
    rejected = client.post(
        f"{BASE}/{second['id']}/reject",
        headers=approver_headers,
    )
    assert rejected.status_code == 200

    listed = client.get(BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    rows = listed.json()
    pending_count = len([row for row in rows if row["status"] == "pending"])
    approved_count = len([row for row in rows if row["status"] == "approved"])
    rejected_count = len([row for row in rows if row["status"] == "rejected"])
    assert pending_count >= 1
    assert approved_count >= 2
    assert rejected_count >= 1

    summary_policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Summary Duration Policy")
    duration_30 = _create_exception(client, org["org_headers"], policy_id=summary_policy["id"], title="d30")
    duration_60 = _create_exception(client, org["org_headers"], policy_id=summary_policy["id"], title="d60")
    approve_30 = client.post(
        f"{BASE}/{duration_30['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=30)).isoformat()},
    )
    assert approve_30.status_code == 200
    approve_60 = client.post(
        f"{BASE}/{duration_60['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=60)).isoformat()},
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
        json={"expiry_date": (date.today() + timedelta(days=5)).isoformat()},
    )
    assert approve_cross.status_code == 404


def test_verify_sod_applies_symmetrically_to_reject_not_just_approve(client):
    """Regression: reject previously had no segregation-of-duties check at all, while
    approve correctly rejected the requester approving their own exception. A requester
    must not be able to reject (i.e. unilaterally close out) their own exception either."""
    org = bootstrap_org_user(client, email_prefix="a32-sod-reject")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="SoD Reject Policy")
    exception = _create_exception(client, org["org_headers"], policy_id=policy["id"], title="self-reject")

    self_reject = client.post(f"{BASE}/{exception['id']}/reject", headers=org["org_headers"])
    print("SELF REJECT:", self_reject.status_code, self_reject.json())
    assert self_reject.status_code == 409, "BUG: requester was able to reject their own exception (no SoD check)"
    assert "cannot be requester" in self_reject.json()["detail"].lower()

    row_after = self_reject if self_reject.status_code == 200 else None
    assert row_after is None, "exception must remain pending after a blocked self-reject attempt"


def _archive_policy(client, headers: dict[str, str], policy_id: str) -> None:
    r1 = client.patch(f"/api/v1/compliance/policies/{policy_id}", headers=headers, json={"status": "under_review"})
    assert r1.status_code == 200
    r2 = client.patch(f"/api/v1/compliance/policies/{policy_id}", headers=headers, json={"status": "approved"})
    assert r2.status_code == 200
    r3 = client.patch(f"/api/v1/compliance/policies/{policy_id}", headers=headers, json={"status": "deprecated"})
    assert r3.status_code == 200
    r4 = client.post(f"/api/v1/compliance/policies/{policy_id}/archive", headers=headers, json={"reason": "retired"})
    assert r4.status_code == 200


def test_a32_cannot_request_exception_against_archived_policy(client):
    """Edge case: an exception request against a policy that has since been archived must be
    rejected outright, rather than silently created against a policy no one is enforcing anymore."""
    org = bootstrap_org_user(client, email_prefix="a32-archived-policy")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Soon Archived")
    _archive_policy(client, org["org_headers"], policy["id"])

    response = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "policy_id": policy["id"],
            "reason": "trying to except an archived policy",
            "compensating_measure_description": "n/a",
        },
    )
    assert response.status_code == 400
    assert "archived" in response.json()["detail"].lower()


def test_a32_exception_flags_stale_policy_version_and_archived_status(client):
    """Context-consciousness: once a policy is re-versioned or archived after an exception was
    granted, the exception record must surface that drift instead of silently implying the
    exception still applies to the current, live policy text."""
    org = bootstrap_org_user(client, email_prefix="a32-stale-flag")
    policy = _create_policy(client, org["org_headers"], owner_user_id=org["user_id"], title="Drifting Policy", version="1.0")
    created = _create_exception(client, org["org_headers"], policy_id=policy["id"])

    detail = client.get(f"{BASE}/{created['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    body = detail.json()
    assert body["policy_is_archived"] is False
    assert body["policy_current_version"] == "1.0"

    # Bump the live policy version out from under the exception.
    bump = client.patch(
        f"/api/v1/compliance/policies/{policy['id']}",
        headers=org["org_headers"],
        json={"version": "2.0"},
    )
    assert bump.status_code == 200

    detail_after = client.get(f"{BASE}/{created['id']}", headers=org["org_headers"])
    assert detail_after.status_code == 200
    body_after = detail_after.json()
    assert body_after["policy_current_version"] == "2.0"

    # The v1 richer read surface (PATCH response) snapshots policy_version at request time and
    # must now report the exception as stale against the live (bumped) policy version.
    patched = client.patch(
        f"/api/v1/compliance/policy-exceptions/{created['id']}",
        headers=org["org_headers"],
        json={"requestor_scope": "re-checked"},
    )
    assert patched.status_code == 200
    patched_body = patched.json()
    assert patched_body["policy_version_is_stale"] is True
    assert patched_body["policy"]["current_version"] == "2.0"
    assert patched_body["policy"]["status"] == "draft"
