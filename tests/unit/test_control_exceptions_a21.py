from datetime import date, timedelta
import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.control_exception import ControlException
from app.models.control_exception_approval import ControlExceptionApproval
from app.models.control_monitoring_alert import ControlMonitoringAlert
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.compliance.services.control_exception_service import ControlExceptionService
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

BASE = "/api/v1/compliance/control-exceptions"


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


def _create_control(client, headers: dict[str, str], *, title: str) -> dict:
    response = client.post(
        "/api/v1/controls",
        headers=headers,
        json={"title": title, "control_type": "policy", "criticality": "medium"},
    )
    assert response.status_code == 201
    return response.json()


def _create_exception(
    client,
    headers: dict[str, str],
    *,
    control_id: str,
    owner_user_id: str,
    exception_type: str = "temporary",
    effective_date_value: date | None = None,
    expiry_date_value: date | None = None,
    approvers: list[dict] | None = None,
    compensating_control_id: str | None = None,
) -> dict:
    effective = effective_date_value or (date.today() - timedelta(days=1))
    expiry = expiry_date_value if expiry_date_value is not None else (date.today() + timedelta(days=30))
    payload = {
        "control_id": control_id,
        "title": "Exception Request",
        "description": "Cannot meet control temporarily",
        "exception_type": exception_type,
        "risk_acceptance_reason": "Business continuity window",
        "owner_user_id": owner_user_id,
        "effective_date": effective.isoformat(),
        "expiry_date": expiry.isoformat() if expiry else None,
        "tags_json": {"env": "test"},
        "notes": "tracking",
    }
    if approvers is not None:
        payload["approvers"] = approvers
    if compensating_control_id is not None:
        payload["compensating_control_id"] = compensating_control_id

    response = client.post(BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_a21_create_exception_and_validation_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a21-create")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a21-owner@example.com")
    control = _create_control(client, org["org_headers"], title="A21 Main Control")

    created = _create_exception(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id))
    assert created["status"] == "pending_approval"
    assert created["exception_type"] == "temporary"

    missing_expiry = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "title": "bad",
            "description": "bad",
            "exception_type": "temporary",
            "risk_acceptance_reason": "reason",
            "owner_user_id": str(owner.id),
            "effective_date": date.today().isoformat(),
            "expiry_date": None,
        },
    )
    assert missing_expiry.status_code == 422

    permanent_with_expiry = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "title": "bad",
            "description": "bad",
            "exception_type": "permanent",
            "risk_acceptance_reason": "reason",
            "owner_user_id": str(owner.id),
            "effective_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=10)).isoformat(),
        },
    )
    assert permanent_with_expiry.status_code == 422

    bad_dates = client.post(
        BASE,
        headers=org["org_headers"],
        json={
            "control_id": control["id"],
            "title": "bad",
            "description": "bad",
            "exception_type": "temporary",
            "risk_acceptance_reason": "reason",
            "owner_user_id": str(owner.id),
            "effective_date": date.today().isoformat(),
            "expiry_date": date.today().isoformat(),
        },
    )
    assert bad_dates.status_code == 422


def test_a21_compensating_control_and_owner_membership_validation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a21-comp-a")
    org2 = bootstrap_org_user(client, email_prefix="a21-comp-b")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "a21-owner1@example.com")
    owner2 = _create_active_user_with_role(db_session, org2["organization_id"], "a21-owner2@example.com")

    control1 = _create_control(client, org1["org_headers"], title="A21 c1")
    control2 = _create_control(client, org2["org_headers"], title="A21 c2")

    bad_comp = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "title": "bad comp",
            "description": "bad comp",
            "exception_type": "temporary",
            "risk_acceptance_reason": "reason",
            "compensating_control_id": control2["id"],
            "owner_user_id": str(owner1.id),
            "effective_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=5)).isoformat(),
        },
    )
    assert bad_comp.status_code == 404

    bad_owner = client.post(
        BASE,
        headers=org1["org_headers"],
        json={
            "control_id": control1["id"],
            "title": "bad owner",
            "description": "bad owner",
            "exception_type": "temporary",
            "risk_acceptance_reason": "reason",
            "owner_user_id": str(owner2.id),
            "effective_date": date.today().isoformat(),
            "expiry_date": (date.today() + timedelta(days=5)).isoformat(),
        },
    )
    assert bad_owner.status_code == 422


def test_a21_approval_lifecycle_and_four_eyes(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a21-approve")
    requester_headers = org["org_headers"]
    requester_id = org["user_id"]

    step1 = _create_active_user_with_role(db_session, org["organization_id"], "a21-step1@example.com")
    step2 = _create_active_user_with_role(db_session, org["organization_id"], "a21-step2@example.com")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a21-owner@example.com")

    control = _create_control(client, requester_headers, title="A21 Approval Control")

    same_user_approval = _create_exception(
        client,
        requester_headers,
        control_id=control["id"],
        owner_user_id=str(owner.id),
    )
    own_approve = client.post(
        f"{BASE}/{same_user_approval['id']}/approve",
        headers=requester_headers,
        json={"decision_notes": "self"},
    )
    assert own_approve.status_code == 422

    single = _create_exception(
        client,
        requester_headers,
        control_id=control["id"],
        owner_user_id=str(owner.id),
    )

    step1_token = login_user(client, step1.email)
    step1_headers = org_headers(step1_token, org["organization_id"])
    approved_single = client.post(
        f"{BASE}/{single['id']}/approve",
        headers=step1_headers,
        json={"decision_notes": "ok"},
    )
    assert approved_single.status_code == 200
    assert approved_single.json()["status"] == "active"

    multi = _create_exception(
        client,
        requester_headers,
        control_id=control["id"],
        owner_user_id=str(owner.id),
        approvers=[
            {"user_id": str(step1.id), "sequence": 1},
            {"user_id": str(step2.id), "sequence": 2},
        ],
    )

    step1_decision = client.post(
        f"{BASE}/{multi['id']}/approve",
        headers=step1_headers,
        json={"decision_notes": "step1"},
    )
    assert step1_decision.status_code == 200
    assert step1_decision.json()["status"] == "pending_approval"

    detail_after_step1 = client.get(f"{BASE}/{multi['id']}", headers=requester_headers)
    assert detail_after_step1.status_code == 200
    approvals = detail_after_step1.json()["approvals"]
    assert approvals[0]["status"] == "approved"
    assert approvals[1]["status"] == "pending"

    step2_token = login_user(client, step2.email)
    step2_headers = org_headers(step2_token, org["organization_id"])
    step2_decision = client.post(
        f"{BASE}/{multi['id']}/approve",
        headers=step2_headers,
        json={"decision_notes": "step2"},
    )
    assert step2_decision.status_code == 200
    assert step2_decision.json()["status"] == "active"
    assert step2_decision.json()["approved_by_user_id"] == str(step2.id)

    _ = requester_id


def test_a21_reject_revoke_and_state_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a21-reject")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a21-owner2@example.com")
    approver = _create_active_user_with_role(db_session, org["organization_id"], "a21-approver2@example.com")
    control = _create_control(client, org["org_headers"], title="A21 Reject Control")

    pending = _create_exception(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
        approvers=[
            {"user_id": str(approver.id), "sequence": 1},
            {"user_id": str(owner.id), "sequence": 2},
        ],
    )

    missing_reason = client.post(f"{BASE}/{pending['id']}/reject", headers=org["org_headers"], json={})
    assert missing_reason.status_code == 422

    rejected = client.post(
        f"{BASE}/{pending['id']}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "risk too high"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    detail = client.get(f"{BASE}/{pending['id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert all(step["status"] in {"skipped", "approved", "rejected"} for step in detail.json()["approvals"])

    revoke_non_active = client.post(
        f"{BASE}/{pending['id']}/revoke",
        headers=org["org_headers"],
        json={"revocation_reason": "should fail"},
    )
    assert revoke_non_active.status_code == 422

    another = _create_exception(client, org["org_headers"], control_id=control["id"], owner_user_id=str(owner.id))

    approver_token = login_user(client, approver.email)
    approver_headers = org_headers(approver_token, org["organization_id"])
    active = client.post(f"{BASE}/{another['id']}/approve", headers=approver_headers, json={"decision_notes": "ok"})
    assert active.status_code == 200
    assert active.json()["status"] == "active"

    missing_revoke_reason = client.post(f"{BASE}/{another['id']}/revoke", headers=org["org_headers"], json={})
    assert missing_revoke_reason.status_code == 422

    revoked = client.post(
        f"{BASE}/{another['id']}/revoke",
        headers=org["org_headers"],
        json={"revocation_reason": "conditions changed"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"


def test_a21_expiry_check_summary_filters_status_lookup_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="a21-exp-a")
    org2 = bootstrap_org_user(client, email_prefix="a21-exp-b")

    owner1 = _create_active_user_with_role(db_session, org1["organization_id"], "a21-exp-owner1@example.com")
    approver1 = _create_active_user_with_role(db_session, org1["organization_id"], "a21-exp-approver1@example.com")
    owner2 = _create_active_user_with_role(db_session, org2["organization_id"], "a21-exp-owner2@example.com")

    control_past = _create_control(client, org1["org_headers"], title="A21 past")
    control_soon = _create_control(client, org1["org_headers"], title="A21 soon")
    control_far = _create_control(client, org1["org_headers"], title="A21 far")
    control_none = _create_control(client, org1["org_headers"], title="A21 none")
    control_org2 = _create_control(client, org2["org_headers"], title="A21 org2")

    approver_headers = org_headers(login_user(client, approver1.email), org1["organization_id"])

    past_exc = _create_exception(
        client,
        org1["org_headers"],
        control_id=control_past["id"],
        owner_user_id=str(owner1.id),
        effective_date_value=date.today() - timedelta(days=10),
        expiry_date_value=date.today() - timedelta(days=1),
    )
    soon_exc = _create_exception(
        client,
        org1["org_headers"],
        control_id=control_soon["id"],
        owner_user_id=str(owner1.id),
        effective_date_value=date.today() - timedelta(days=1),
        expiry_date_value=date.today() + timedelta(days=10),
    )
    far_exc = _create_exception(
        client,
        org1["org_headers"],
        control_id=control_far["id"],
        owner_user_id=str(owner1.id),
        effective_date_value=date.today() - timedelta(days=1),
        expiry_date_value=date.today() + timedelta(days=60),
    )

    _ = _create_exception(
        client,
        org2["org_headers"],
        control_id=control_org2["id"],
        owner_user_id=str(owner2.id),
        effective_date_value=date.today() - timedelta(days=1),
        expiry_date_value=date.today() + timedelta(days=15),
    )

    for exc in [past_exc, soon_exc, far_exc]:
        approved = client.post(f"{BASE}/{exc['id']}/approve", headers=approver_headers, json={"decision_notes": "activate"})
        assert approved.status_code == 200

    # service-level lookup for active control exception context
    service = ControlExceptionService(db_session)
    active_for_soon = service.get_control_exception_status(uuid.UUID(control_soon["id"]), uuid.UUID(org1["organization_id"]))
    none_for_control = service.get_control_exception_status(uuid.UUID(control_none["id"]), uuid.UUID(org1["organization_id"]))
    assert active_for_soon is not None
    assert none_for_control is None

    pre_check = client.post(f"{BASE}/check-expiry", headers=org1["org_headers"])
    assert pre_check.status_code == 200
    assert pre_check.json()["expired_count"] == 1
    assert pre_check.json()["expired_exceptions"][0]["id"] == past_exc["id"]

    # idempotent second run
    second_check = client.post(f"{BASE}/check-expiry", headers=org1["org_headers"])
    assert second_check.status_code == 200
    assert second_check.json()["expired_count"] == 0

    expired_row = db_session.execute(select(ControlException).where(ControlException.id == uuid.UUID(past_exc["id"]))).scalar_one()
    assert expired_row.status == "expired"
    assert expired_row.auto_expired_at is not None

    alert_row = db_session.execute(
        select(ControlMonitoringAlert).where(
            ControlMonitoringAlert.organization_id == uuid.UUID(org1["organization_id"]),
            ControlMonitoringAlert.control_id == uuid.UUID(control_past["id"]),
            ControlMonitoringAlert.alert_type == "manual",
            ControlMonitoringAlert.severity == "high",
        )
    ).scalar_one_or_none()
    assert alert_row is not None

    summary = client.get(f"{BASE}/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["expiring_soon"] == 1
    assert summary_body["controls_with_active_exception"] == 2

    expiring_only = client.get(f"{BASE}?expiring_within_days=30", headers=org1["org_headers"])
    assert expiring_only.status_code == 200
    ids = {row["id"] for row in expiring_only.json()}
    assert soon_exc["id"] in ids
    assert far_exc["id"] not in ids

    cross_detail = client.get(f"{BASE}/{soon_exc['id']}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    cross_list = client.get(BASE, headers=org2["org_headers"])
    assert cross_list.status_code == 200
    assert all(row["organization_id"] == org2["organization_id"] for row in cross_list.json())


def test_a21_audit_events_cover_lifecycle_transitions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a21-audit")
    owner = _create_active_user_with_role(db_session, org["organization_id"], "a21-audit-owner@example.com")
    approver = _create_active_user_with_role(db_session, org["organization_id"], "a21-audit-approver@example.com")
    control = _create_control(client, org["org_headers"], title="A21 Audit Control")

    chain = _create_exception(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
        approvers=[{"user_id": str(approver.id), "sequence": 1}],
        effective_date_value=date.today() - timedelta(days=10),
        expiry_date_value=date.today() - timedelta(days=2),
    )

    approver_headers = org_headers(login_user(client, approver.email), org["organization_id"])
    ok = client.post(f"{BASE}/{chain['id']}/approve", headers=approver_headers, json={"decision_notes": "approve"})
    assert ok.status_code == 200

    expired = client.post(f"{BASE}/check-expiry", headers=org["org_headers"])
    assert expired.status_code == 200
    assert expired.json()["expired_count"] == 1

    rejected_candidate = _create_exception(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
    )
    rej = client.post(
        f"{BASE}/{rejected_candidate['id']}/reject",
        headers=org["org_headers"],
        json={"rejection_reason": "not acceptable"},
    )
    assert rej.status_code == 200

    active_candidate = _create_exception(
        client,
        org["org_headers"],
        control_id=control["id"],
        owner_user_id=str(owner.id),
    )
    act = client.post(f"{BASE}/{active_candidate['id']}/approve", headers=approver_headers, json={"decision_notes": "ok"})
    assert act.status_code == 200
    rev = client.post(
        f"{BASE}/{active_candidate['id']}/revoke",
        headers=org["org_headers"],
        json={"revocation_reason": "superseded"},
    )
    assert rev.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "control_exception.created" in actions
    assert "control_exception.approval_step_completed" in actions
    assert "control_exception.approved" in actions
    assert "control_exception.rejected" in actions
    assert "control_exception.revoked" in actions
    assert "control_exception.expired" in actions

    approvals = db_session.execute(select(ControlExceptionApproval)).scalars().all()
    assert approvals
