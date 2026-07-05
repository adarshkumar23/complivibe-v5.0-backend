from __future__ import annotations

import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user, org_headers

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_user_with_permissions(db_session, org_id: str, email: str, permission_codes: set[str]) -> User:
    role = Role(
        organization_id=uuid.UUID(org_id),
        name=f"custom-{email.split('@')[0]}",
        description="Custom test role",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.flush()

    permission_ids = {
        row.id
        for row in db_session.execute(
            select(Permission).where(Permission.key.in_(permission_codes))
        ).scalars()
    }
    for permission_id in permission_ids:
        db_session.add(RolePermission(role_id=role.id, permission_id=permission_id))

    user = User(
        email=email,
        full_name="Custom Role User",
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
            invited_by=None,
        )
    )
    db_session.commit()
    return user


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    resp = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _login_and_headers(client, user: User, org_id: str) -> dict[str, str]:
    resp = client.post("/api/v1/auth/login", json={"email": user.email, "password": "Pass1234!@"})
    assert resp.status_code == 200
    return org_headers(resp.json()["access_token"], org_id)


def test_aibom_and_model_card_permissions_denied_without_new_perms(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rbac-owner")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "RBAC System")

    limited_user = _create_user_with_permissions(
        db_session,
        org["organization_id"],
        "aibom-limited@example.com",
        {"ai_systems:read", "ai_systems:write", "ai_governance:read", "ai_governance:write"},
    )
    limited_headers = _login_and_headers(client, limited_user, org["organization_id"])

    # AIBOM read/write should be denied without ai_bom:* permissions.
    assert client.get(f"{SYSTEMS_BASE}/{system_id}/aibom/latest", headers=limited_headers).status_code == 403
    assert (
        client.post(f"{SYSTEMS_BASE}/{system_id}/aibom", headers=limited_headers, json={"notes": "n"}).status_code
        == 403
    )

    # Model card read/write/publish should be denied without model_registry:* permissions.
    assert client.get(f"{SYSTEMS_BASE}/{system_id}/model-card", headers=limited_headers).status_code == 403
    assert client.get(f"{SYSTEMS_BASE}/{system_id}/model-cards", headers=limited_headers).status_code == 403
    assert (
        client.post(
            f"{SYSTEMS_BASE}/{system_id}/model-card",
            headers=limited_headers,
            json={"intended_purpose": "x", "contact_owner_id": str(limited_user.id)},
        ).status_code
        == 403
    )


def test_aibom_and_model_card_permitted_with_new_perms(client, db_session):
    org = bootstrap_org_user(client, email_prefix="rbac-granted")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "RBAC Granted System")

    privileged_user = _create_user_with_permissions(
        db_session,
        org["organization_id"],
        "aibom-privileged@example.com",
        {
            "ai_systems:read",
            "ai_systems:write",
            "ai_governance:read",
            "ai_governance:write",
            "ai_bom:read",
            "ai_bom:write",
            "model_registry:read",
            "model_registry:write",
        },
    )
    privileged_headers = _login_and_headers(client, privileged_user, org["organization_id"])

    # AIBOM lifecycle permitted.
    create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom",
        headers=privileged_headers,
        json={"notes": "initial"},
    )
    assert create.status_code == 201

    latest = client.get(f"{SYSTEMS_BASE}/{system_id}/aibom/latest", headers=privileged_headers)
    assert latest.status_code == 200

    diff = client.get(f"{SYSTEMS_BASE}/{system_id}/aibom/diff?v1=1&v2=1", headers=privileged_headers)
    assert diff.status_code == 200

    # Model card lifecycle permitted.
    card = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-card",
        headers=privileged_headers,
        json={
            "intended_purpose": "Assist support triage",
            "known_limitations": ["May miss context"],
            "approved_use_cases": ["Ticket routing"],
            "prohibited_use_cases": ["Medical diagnosis"],
            "contact_owner_id": str(privileged_user.id),
        },
    )
    assert card.status_code == 201
    card_id = card.json()["id"]

    assert client.get(f"{SYSTEMS_BASE}/{system_id}/model-card", headers=privileged_headers).status_code == 200
    assert client.get(f"{SYSTEMS_BASE}/{system_id}/model-cards", headers=privileged_headers).status_code == 200

    update = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/model-cards/{card_id}",
        headers=privileged_headers,
        json={"intended_purpose": "Updated purpose"},
    )
    assert update.status_code == 200

    publish = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-cards/{card_id}/publish",
        headers=privileged_headers,
    )
    assert publish.status_code == 200
    assert publish.json()["status"] == "published"
