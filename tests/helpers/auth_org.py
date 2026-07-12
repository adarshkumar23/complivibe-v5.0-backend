from __future__ import annotations

import uuid
from itertools import count
from typing import Any, TypedDict


_EMAIL_COUNTER = count(1)


class BootstrapOrgUserResult(TypedDict):
    user_id: str
    organization_id: str
    access_token: str
    headers: dict[str, str]
    org_headers: dict[str, str]
    email: str


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def org_headers(token: str, organization_id: str) -> dict[str, str]:
    headers = auth_headers(token)
    headers["X-Organization-ID"] = organization_id
    return headers


def login_user(client, email: str, password: str = "Pass1234!@") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def bootstrap_org_user(
    client,
    email_prefix: str = "test",
    password: str = "Pass1234!@",
    organization_name: str | None = None,
) -> BootstrapOrgUserResult:
    idx = next(_EMAIL_COUNTER)
    email = f"{email_prefix}-{idx}@example.com"
    org_name = organization_name or f"{email_prefix}-org-{idx}"

    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert register.status_code == 200
    access_token = register.json()["access_token"]

    headers = auth_headers(access_token)
    orgs = client.get("/api/v1/organizations/me", headers=headers)
    assert orgs.status_code == 200
    organization_id = orgs.json()[0]["id"]

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    user_id = me.json()["id"]

    return {
        "user_id": user_id,
        "organization_id": organization_id,
        "access_token": access_token,
        "headers": headers,
        "org_headers": org_headers(access_token, organization_id),
        "email": email,
    }


def bootstrap_admin_org(
    client,
    email_prefix: str = "admin",
    password: str = "Pass1234!@",
    organization_name: str | None = None,
) -> BootstrapOrgUserResult:
    return bootstrap_org_user(
        client,
        email_prefix=email_prefix,
        password=password,
        organization_name=organization_name,
    )


def add_org_member(
    db_session,
    client,
    organization_id: str,
    email: str,
    role_name: str = "admin",
    password: str = "Pass1234!@",
) -> dict[str, str]:
    """Create a second active user in an existing org and return their org-scoped headers.

    Used to obtain a distinct approver in tests, since approval endpoints correctly
    reject a requester approving their own request.
    """
    from app.core.security import get_password_hash
    from app.models.membership import Membership
    from app.models.role import Role
    from app.models.user import User

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

    role = (
        db_session.query(Role)
        .filter(Role.organization_id == uuid.UUID(organization_id), Role.name == role_name)
        .one()
    )
    membership = Membership(
        organization_id=uuid.UUID(organization_id),
        user_id=user.id,
        role_id=role.id,
        status="active",
    )
    db_session.add(membership)
    db_session.commit()

    token = login_user(client, email, password=password)
    return org_headers(token, organization_id)


def bootstrap_governance_manifest(client, organization_headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/organizations/me/governance-settings/evidence-manifests",
        headers=organization_headers,
        json={},
    )
    assert response.status_code == 201
    return response.json()
