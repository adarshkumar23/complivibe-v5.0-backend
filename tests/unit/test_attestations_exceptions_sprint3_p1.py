import hashlib
import uuid
from datetime import UTC, date, datetime, timedelta

from app.compliance.services.policy_exception_service import PolicyExceptionService
from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.policy_attestation import PolicyAttestation
from app.models.policy_exception import PolicyException
from app.models.role import Role
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers


ATTEST_BASE = "/api/v1/compliance/attestation-campaigns"
EXC_BASE = "/api/v1/compliance/policy-exceptions"


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


def _create_policy(client, headers: dict[str, str], owner_user_id: str, title: str) -> dict:
    response = client.post(
        "/api/v1/compliance/policies",
        headers=headers,
        json={
            "title": title,
            "description": "Policy text",
            "policy_type": "access_control",
            "status": "draft",
            "owner_user_id": owner_user_id,
            "version": "1.0",
            "content_url": "https://example.com/policy.txt",
        },
    )
    assert response.status_code == 201
    return response.json()


def _create_campaign(client, headers: dict[str, str], policy_id: str, title: str, attestation_text: str) -> dict:
    response = client.post(
        ATTEST_BASE,
        headers=headers,
        json={
            "policy_id": policy_id,
            "title": title,
            "description": "Quarterly attestation",
            "due_date": (date.today() + timedelta(days=10)).isoformat(),
            "attestation_text": attestation_text,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_s3_p1_attestation_campaign_and_attest_decline_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p1-att")
    member = _create_active_user_with_role(db_session, org["organization_id"], "s3p1-member@example.com")
    policy = _create_policy(client, org["org_headers"], org["user_id"], "S3 Policy")

    shown_text = "Employees must follow secure access and MFA requirements."
    created = _create_campaign(client, org["org_headers"], policy["id"], "S3 Campaign", shown_text)
    campaign = created["campaign"]

    assert campaign["content_hash"] == hashlib.sha256(shown_text.encode()).hexdigest()
    assert created["pending_count"] >= 2  # owner + member

    member_headers = org_headers(login_user(client, member.email), org["organization_id"])
    attested = client.post(f"{ATTEST_BASE}/{campaign['id']}/attest", headers=member_headers, json={})
    assert attested.status_code == 200
    assert attested.json()["status"] == "attested"
    assert attested.json()["attested_at"] is not None

    second = client.post(f"{ATTEST_BASE}/{campaign['id']}/attest", headers=member_headers, json={})
    assert second.status_code == 409

    owner_decline = client.post(
        f"{ATTEST_BASE}/{campaign['id']}/decline",
        headers=org["org_headers"],
        json={"decline_reason": "Need legal clarification"},
    )
    assert owner_decline.status_code == 200
    assert owner_decline.json()["status"] == "declined"

    summary = client.get(f"{ATTEST_BASE}/{campaign['id']}", headers=org["org_headers"])
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_members"] >= 2
    assert payload["attested_count"] >= 1
    assert payload["declined_count"] >= 1

    my_records = client.get("/api/v1/compliance/my-attestations", headers=member_headers)
    assert my_records.status_code == 200
    assert all(r["user_id"] == str(member.id) for r in my_records.json())

    att_row = (
        db_session.query(PolicyAttestation)
        .filter(PolicyAttestation.campaign_id == uuid.UUID(campaign["id"]), PolicyAttestation.user_id == member.id)
        .one()
    )
    assert att_row.status == "attested"


def test_s3_p1_policy_exception_lifecycle_and_sweep(client, db_session):
    org = bootstrap_org_user(client, email_prefix="s3p1-exc")
    approver = _create_active_user_with_role(db_session, org["organization_id"], "s3p1-approver@example.com", role_name="owner")
    policy = _create_policy(client, org["org_headers"], org["user_id"], "Exception Policy")

    created = client.post(
        EXC_BASE,
        headers=org["org_headers"],
        json={
            "policy_id": policy["id"],
            "reason": "Temporary exception required",
            "compensating_measure_description": "Manual review",
        },
    )
    assert created.status_code == 200
    exc_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    self_approve = client.post(
        f"{EXC_BASE}/{exc_id}/approve",
        headers=org["org_headers"],
        json={"expiry_date": (date.today() + timedelta(days=5)).isoformat()},
    )
    assert self_approve.status_code == 409

    approver_headers = org_headers(login_user(client, approver.email), org["organization_id"])
    approved = client.post(
        f"{EXC_BASE}/{exc_id}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() - timedelta(days=1)).isoformat()},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    # create another to reject
    created2 = client.post(
        EXC_BASE,
        headers=org["org_headers"],
        json={"policy_id": policy["id"], "reason": "Reject me"},
    )
    assert created2.status_code == 200

    rejected = client.post(f"{EXC_BASE}/{created2.json()['id']}/reject", headers=approver_headers)
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    expired_count = PolicyExceptionService(db_session).expire_overdue_exceptions(uuid.UUID(org["organization_id"]))
    db_session.commit()
    assert expired_count >= 1

    expired_row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(exc_id)).one()
    assert expired_row.status == "expired"
    assert expired_row.expired_at is not None

    # future-dated approved exceptions must remain approved after sweep
    created3 = client.post(
        EXC_BASE,
        headers=org["org_headers"],
        json={"policy_id": policy["id"], "reason": "Future expiry should remain approved"},
    )
    assert created3.status_code == 200
    exc_future_id = created3.json()["id"]

    approved_future = client.post(
        f"{EXC_BASE}/{exc_future_id}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() + timedelta(days=30)).isoformat()},
    )
    assert approved_future.status_code == 200
    assert approved_future.json()["status"] == "approved"

    _ = PolicyExceptionService(db_session).expire_overdue_exceptions(uuid.UUID(org["organization_id"]))
    db_session.commit()
    future_row = db_session.query(PolicyException).filter(PolicyException.id == uuid.UUID(exc_future_id)).one()
    assert future_row.status == "approved"


def test_s3_p1_cross_org_isolation_and_audit_logs(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="s3p1-org-a")
    org_b = bootstrap_org_user(client, email_prefix="s3p1-org-b")
    pending_member = _create_active_user_with_role(db_session, org_a["organization_id"], "s3p1-org-a-member@example.com")

    policy_a = _create_policy(client, org_a["org_headers"], org_a["user_id"], "Org A Policy")
    campaign = _create_campaign(client, org_a["org_headers"], policy_a["id"], "Org A Campaign", "text")

    forbidden_campaign = client.get(f"{ATTEST_BASE}/{campaign['campaign']['id']}", headers=org_b["org_headers"])
    assert forbidden_campaign.status_code == 404
    forbidden_attest = client.post(f"{ATTEST_BASE}/{campaign['campaign']['id']}/attest", headers=org_b["org_headers"], json={})
    assert forbidden_attest.status_code == 404

    ex = client.post(
        EXC_BASE,
        headers=org_a["org_headers"],
        json={"policy_id": policy_a["id"], "reason": "Org A only"},
    )
    assert ex.status_code == 200

    forbidden_exc = client.get(f"{EXC_BASE}/{ex.json()['id']}", headers=org_b["org_headers"])
    assert forbidden_exc.status_code == 404

    # Trigger attested/declined + approved/rejected to verify audit actions exist.
    owner_attest = client.post(f"{ATTEST_BASE}/{campaign['campaign']['id']}/attest", headers=org_a["org_headers"], json={})
    assert owner_attest.status_code in {200, 409}
    member_headers = org_headers(login_user(client, pending_member.email), org_a["organization_id"])
    owner_decline = client.post(
        f"{ATTEST_BASE}/{campaign['campaign']['id']}/decline",
        headers=member_headers,
        json={"decline_reason": "n/a"},
    )
    assert owner_decline.status_code == 200

    approver = _create_active_user_with_role(db_session, org_a["organization_id"], "s3p1-audit-approver@example.com", role_name="owner")
    approver_headers = org_headers(login_user(client, approver.email), org_a["organization_id"])
    _ = client.post(
        f"{EXC_BASE}/{ex.json()['id']}/approve",
        headers=approver_headers,
        json={"expiry_date": (date.today() - timedelta(days=1)).isoformat()},
    )

    ex2 = client.post(EXC_BASE, headers=org_a["org_headers"], json={"policy_id": policy_a["id"], "reason": "reject"})
    assert ex2.status_code == 200
    _ = client.post(f"{EXC_BASE}/{ex2.json()['id']}/reject", headers=approver_headers)

    _ = PolicyExceptionService(db_session).expire_overdue_exceptions(uuid.UUID(org_a["organization_id"]))
    db_session.commit()

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org_a["organization_id"]))
        .all()
    }
    assert "attestation.campaign_created" in actions
    assert "attestation.attested" in actions
    assert "attestation.declined" in actions
    assert "policy_exception.requested" in actions
    assert "policy_exception.approved" in actions
    assert "policy_exception.rejected" in actions
    assert "policy_exception.expired" in actions
