from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.base import Base
from app.models.access_certification import AccessCertificationCampaign, AccessCertificationItem
from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, org_headers

BASE_URL = "/api/v1/access-certifications"
ACCESS_CERT_PERMISSIONS = {"recertification:read", "recertification:write"}


@pytest.fixture(autouse=True)
def _install_access_certification_router_and_tables(client, _test_engine):
    Base.metadata.create_all(
        bind=_test_engine,
        tables=[AccessCertificationCampaign.__table__, AccessCertificationItem.__table__],
    )
    if not getattr(client.app.state, "access_certification_router_installed", False):
        from app.api.v1.access_certifications import router as access_certification_router

        client.app.include_router(access_certification_router, prefix="/api/v1")
        client.app.state.access_certification_router_installed = True



def _grant_access_cert_permissions(db_session, org_id: str, user_id: str) -> None:
    membership = db_session.execute(
        select(Membership).where(
            Membership.organization_id == uuid.UUID(org_id),
            Membership.user_id == uuid.UUID(user_id),
        )
    ).scalar_one()

    for code in ACCESS_CERT_PERMISSIONS:
        permission = db_session.execute(select(Permission).where(Permission.key == code)).scalar_one_or_none()
        if permission is None:
            permission = Permission(key=code, description=f"Access certification {code}")
            db_session.add(permission)
            db_session.flush()
        existing = db_session.execute(
            select(RolePermission).where(
                RolePermission.role_id == membership.role_id,
                RolePermission.permission_id == permission.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            db_session.add(RolePermission(role_id=membership.role_id, permission_id=permission.id))
    db_session.commit()



def _create_active_user_with_access_cert_permissions(db_session, org_id: str, email: str) -> User:
    role = Role(
        organization_id=uuid.UUID(org_id),
        name=f"access-cert-{email.split('@')[0]}",
        description="Access certification reviewer",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.flush()

    for code in ACCESS_CERT_PERMISSIONS:
        permission = db_session.execute(select(Permission).where(Permission.key == code)).scalar_one_or_none()
        if permission is None:
            permission = Permission(key=code, description=f"Access certification {code}")
            db_session.add(permission)
            db_session.flush()
        db_session.add(RolePermission(role_id=role.id, permission_id=permission.id))

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



def _login_headers(client, user: User, org_id: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Pass1234!@"})
    assert response.status_code == 200
    return org_headers(response.json()["access_token"], org_id)



def test_access_certification_campaign_crud_and_archive_audits(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t43-owner")
    _grant_access_cert_permissions(db_session, org["organization_id"], org["user_id"])
    reviewer = _create_active_user_with_access_cert_permissions(db_session, org["organization_id"], "t43-reviewer@example.com")

    created = client.post(
        f"{BASE_URL}/campaigns",
        headers=org["org_headers"],
        json={
            "name": "Quarterly access review",
            "description": "Q1 apps",
            "status": "active",
            "scope_type": "systems",
            "items": [
                {
                    "user_id": org["user_id"],
                    "reviewer_user_id": str(reviewer.id),
                    "system_key": "okta",
                    "system_name": "Okta",
                    "access_level": "admin",
                }
            ],
        },
    )
    assert created.status_code == 201
    body = created.json()
    campaign_id = body["id"]
    assert body["status"] == "active"
    assert body["total_items"] == 1
    assert body["pending_items"] == 1

    listed = client.get(f"{BASE_URL}/campaigns", headers=org["org_headers"])
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [campaign_id]

    updated = client.patch(
        f"{BASE_URL}/campaigns/{campaign_id}",
        headers=org["org_headers"],
        json={"description": "Q1 critical apps", "due_date": "2026-09-30"},
    )
    assert updated.status_code == 200
    assert updated.json()["description"] == "Q1 critical apps"
    assert updated.json()["due_date"] == "2026-09-30"

    archived = client.delete(f"{BASE_URL}/campaigns/{campaign_id}", headers=org["org_headers"])
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    hidden = client.get(f"{BASE_URL}/campaigns", headers=org["org_headers"])
    assert hidden.status_code == 200
    assert hidden.json() == []

    actions = {
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    }
    assert "access_certification_campaign.created" in actions
    assert "access_certification_item.created" in actions
    assert "access_certification_campaign.updated" in actions
    assert "access_certification_campaign.archived" in actions



def test_my_certifications_submit_decision_and_complete_campaign(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t43-decision")
    _grant_access_cert_permissions(db_session, org["organization_id"], org["user_id"])
    reviewer = _create_active_user_with_access_cert_permissions(db_session, org["organization_id"], "t43-manager@example.com")
    reviewer_headers = _login_headers(client, reviewer, org["organization_id"])

    created = client.post(
        f"{BASE_URL}/campaigns",
        headers=org["org_headers"],
        json={
            "name": "Manager review",
            "status": "active",
            "items": [
                {
                    "user_id": org["user_id"],
                    "reviewer_user_id": str(reviewer.id),
                    "system_key": "github",
                    "system_name": "GitHub",
                    "access_level": "maintainer",
                }
            ],
        },
    )
    assert created.status_code == 201
    campaign_id = created.json()["id"]
    item_id = created.json()["items"][0]["id"]

    mine = client.get(f"{BASE_URL}/my-certifications", headers=reviewer_headers)
    assert mine.status_code == 200
    assert [item["id"] for item in mine.json()] == [item_id]

    blocked = client.post(
        f"{BASE_URL}/items/{item_id}/decision",
        headers=org["org_headers"],
        json={"decision": "certified", "comment": "owner cannot certify this assigned item"},
    )
    assert blocked.status_code == 403

    decided = client.post(
        f"{BASE_URL}/items/{item_id}/decision",
        headers=reviewer_headers,
        json={"decision": "revoked", "comment": "Access no longer required"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "revoked"
    assert decided.json()["decision"] == "revoked"
    assert decided.json()["decided_by_user_id"] == str(reviewer.id)

    detail = client.get(f"{BASE_URL}/campaigns/{campaign_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    assert detail.json()["pending_items"] == 0
    assert detail.json()["revoked_items"] == 1

    actions = [
        row.action
        for row in db_session.query(AuditLog)
        .filter(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    ]
    assert "access_certification_item.decision_submitted" in actions
    assert "access_certification_campaign.completed" in actions
