from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.audit_log import AuditLog
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.models.vendor_mitigation_action import VendorMitigationAction
from app.models.vendor_mitigation_case import VendorMitigationCase
from app.models.vendor_remediation_portal_token import VendorRemediationPortalToken
from tests.helpers.auth_org import bootstrap_org_user, login_user, org_headers

VENDORS_BASE = "/api/v1/compliance/vendors"
MITIGATION_BASE = "/api/v1/compliance/vendor-mitigation"
PORTAL_BASE = "/api/v1/vendor-remediation-portal"


def _create_user_with_role(db_session, org_id: str, email: str, role_name: str) -> User:
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


def _create_vendor(client, headers: dict[str, str], owner_user_id: str, name: str = "Portal Vendor") -> dict:
    resp = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "primary_contact_name": "Vendor Contact",
            "primary_contact_email": "remediation@vendor.example",
            "risk_tier": "high",
            "status": "active",
            "owner_user_id": owner_user_id,
            "data_access": True,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_assessment(client, headers: dict[str, str], vendor_id: str) -> dict:
    resp = client.post(
        f"{VENDORS_BASE}/{vendor_id}/assessments",
        headers=headers,
        json={
            "title": "Portal Assessment",
            "assessment_type": "initial",
            "overall_rating": "needs_improvement",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_case(client, headers: dict[str, str], vendor_id: str, assessment_id: str, owner_user_id: str) -> dict:
    resp = client.post(
        f"{MITIGATION_BASE}/cases",
        headers=headers,
        json={
            "vendor_id": vendor_id,
            "assessment_id": assessment_id,
            "title": "Evidence remediation",
            "description": "Vendor must remediate assessment gap",
            "severity": "high",
            "assigned_owner_id": owner_user_id,
            "due_date": (date.today() + timedelta(days=14)).isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _create_action(client, headers: dict[str, str], case_id: str, title: str, assigned_to_vendor: bool = True) -> dict:
    resp = client.post(
        f"{MITIGATION_BASE}/cases/{case_id}/actions",
        headers=headers,
        json={
            "title": title,
            "description": f"{title} description",
            "action_type": "documentation",
            "assigned_to_vendor": assigned_to_vendor,
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _setup_case_with_actions(client, org: dict) -> tuple[dict, dict, dict, dict]:
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])
    assessment = _create_assessment(client, org["org_headers"], vendor["id"])
    case = _create_case(client, org["org_headers"], vendor["id"], assessment["id"], org["user_id"])
    action_a = _create_action(client, org["org_headers"], case["id"], "Upload attestation")
    action_b = _create_action(client, org["org_headers"], case["id"], "Internal follow-up", assigned_to_vendor=False)
    return vendor, case, action_a, action_b


def _create_token(client, headers: dict[str, str], case_id: str, scoped_action_ids: list[str] | None = None) -> dict:
    payload = {
        "case_id": case_id,
        "vendor_contact_email": "remediation@vendor.example",
        "vendor_contact_name": "Vendor Contact",
        "expires_in_days": 30,
    }
    if scoped_action_ids is not None:
        payload["scoped_action_ids"] = scoped_action_ids
    resp = client.post(f"{PORTAL_BASE}/tokens", headers=headers, json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_t1_5_token_create_returns_plaintext_once_and_stores_hash(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t15-token")
    _vendor, case, action, _internal_action = _setup_case_with_actions(client, org)

    created = _create_token(client, org["org_headers"], case["id"], [action["id"]])
    assert created["plaintext_token"]
    assert created["warning"]

    row = db_session.get(VendorRemediationPortalToken, uuid.UUID(created["token_id"]))
    assert row is not None
    assert row.token_hash != created["plaintext_token"]
    assert len(row.token_hash) == 64

    detail = client.get(f"{PORTAL_BASE}/tokens/{created['token_id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    body = detail.json()
    assert "plaintext_token" not in body
    assert "token_hash" not in body
    assert body["scoped_action_ids"] == [action["id"]]


def test_t1_5_public_portal_auth_wrong_expired_and_revoked(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t15-auth")
    _vendor, case, action, _internal_action = _setup_case_with_actions(client, org)
    created = _create_token(client, org["org_headers"], case["id"], [action["id"]])
    token = created["plaintext_token"]

    wrong = client.get(f"{PORTAL_BASE}/me", headers={"Authorization": "Bearer guessed-token"})
    assert wrong.status_code == 401

    first = client.get(f"{PORTAL_BASE}/me", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200
    assert first.json()["access_count"] == 1
    assert first.json()["vendor"]["name"] == "Portal Vendor"

    row = db_session.get(VendorRemediationPortalToken, uuid.UUID(created["token_id"]))
    row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    row.status = "active"
    db_session.commit()

    expired = client.get(f"{PORTAL_BASE}/me", headers={"Authorization": f"Bearer {token}"})
    assert expired.status_code == 410
    assert expired.json()["detail"] == "Portal token expired"
    db_session.refresh(row)
    assert row.status == "expired"

    revoked_created = _create_token(client, org["org_headers"], case["id"], [action["id"]])
    revoke = client.post(f"{PORTAL_BASE}/tokens/{revoked_created['token_id']}/revoke", headers=org["org_headers"])
    assert revoke.status_code == 200
    revoked = client.get(f"{PORTAL_BASE}/me", headers={"Authorization": f"Bearer {revoked_created['plaintext_token']}"})
    assert revoked.status_code == 403


def test_t1_5_public_actions_are_vendor_scoped_and_submit_evidence_audits(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t15-submit")
    _vendor, case, action, internal_action = _setup_case_with_actions(client, org)
    created = _create_token(client, org["org_headers"], case["id"], [action["id"]])
    portal_headers = {"Authorization": f"Bearer {created['plaintext_token']}"}

    listed = client.get(f"{PORTAL_BASE}/actions", headers=portal_headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [action["id"]]
    assert internal_action["id"] not in [item["id"] for item in listed.json()]

    blocked = client.post(
        f"{PORTAL_BASE}/actions/{internal_action['id']}/submit-evidence",
        headers=portal_headers,
        json={"remediation_notes": "Internal action should not be reachable"},
    )
    assert blocked.status_code == 404

    submitted = client.post(
        f"{PORTAL_BASE}/actions/{action['id']}/submit-evidence",
        headers=portal_headers,
        json={
            "remediation_notes": "Control documentation has been updated and reviewed.",
            "external_reference_url": "https://vendor.example/remediation/evidence",
            "file_name": "remediation-note.pdf",
            "mime_type": "application/pdf",
            "size_bytes": 1234,
        },
    )
    assert submitted.status_code == 200
    body = submitted.json()
    assert body["message"] == "Remediation evidence submitted for review."
    assert body["action"]["status"] == "evidence_submitted"

    action_row = db_session.get(VendorMitigationAction, uuid.UUID(action["id"]))
    case_row = db_session.get(VendorMitigationCase, uuid.UUID(case["id"]))
    evidence = db_session.get(EvidenceItem, uuid.UUID(body["evidence_id"]))
    assert action_row.status == "evidence_submitted"
    assert action_row.evidence_id == evidence.id
    assert case_row.status == "pending_vendor_evidence"
    assert evidence.uploaded_by_user_id is None
    assert evidence.metadata_json["source"] == "vendor_remediation_portal"

    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "vendor_remediation_portal.evidence_submitted",
            AuditLog.entity_id == action_row.id,
        )
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.actor_user_id is None
    assert audit.metadata_json["source"] == "portal"


def test_t1_5_internal_permissions_use_dedicated_portal_permissions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t15-perms")
    _vendor, case, action, _internal_action = _setup_case_with_actions(client, org)
    created = _create_token(client, org["org_headers"], case["id"], [action["id"]])

    reviewer = _create_user_with_role(
        db_session,
        org["organization_id"],
        "t15-reviewer@example.com",
        "reviewer",
    )
    reviewer_token = login_user(client, reviewer.email)
    reviewer_headers = org_headers(reviewer_token, org["organization_id"])

    listed = client.get(f"{PORTAL_BASE}/tokens", headers=reviewer_headers)
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == created["token_id"]

    denied = client.post(
        f"{PORTAL_BASE}/tokens",
        headers=reviewer_headers,
        json={
            "case_id": case["id"],
            "vendor_contact_email": "denied@vendor.example",
            "expires_in_days": 30,
        },
    )
    assert denied.status_code == 403
