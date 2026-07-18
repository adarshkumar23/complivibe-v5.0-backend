"""Permission-gate coverage for the connector marketplace router
(app/api/v1/connector_marketplace.py).

The existing suite (test_connector_marketplace_t34.py + the g1 real-check file)
exercises CRUD, enable/disable, catalog-disabled edges, org isolation and
credential encryption -- but every request is made as the org owner, so the
`connectors:read` / `connectors:write` require_permission gates are never
asserted against a role that lacks them.

Seeded RBAC: owner/admin/compliance_manager hold both connectors:read and
connectors:write; reviewer/auditor/readonly hold neither. There is no seeded
role that holds read-but-not-write, so the "write denied while read allowed"
path is exercised with a bespoke custom role granted only connectors:read.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.permission import Permission
from app.models.role_permission import RolePermission
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/connectors"


def _read_only_connector_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """A member on a custom role granted ONLY connectors:read (no write)."""
    from app.models.role import Role

    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"conn-reader-{uuid.uuid4().hex[:8]}",
        description="connectors:read only",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.flush()

    perm = db_session.execute(
        select(Permission).where(Permission.key == "connectors:read")
    ).scalar_one_or_none()
    if perm is None:
        perm = Permission(key="connectors:read", description="Read connectors")
        db_session.add(perm)
        db_session.flush()
    db_session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


def test_catalog_read_denied_to_role_without_connectors_read(client, db_session):
    """readonly holds neither connectors:read nor connectors:write -> 403 on list."""
    org = bootstrap_org_user(client, email_prefix="conn-perm-read")
    ro = add_org_member(db_session, client, org["organization_id"], "conn-ro@example.com", role_name="readonly")
    resp = client.get(f"{BASE}/catalog", headers=ro)
    assert resp.status_code == 403, resp.text


def test_read_only_role_can_list_but_not_create(client, db_session):
    """A connectors:read-only member can GET the catalog (200) but is refused the
    write endpoint (403) -- proving the create 403 is the write gate, not a
    blanket auth failure."""
    org = bootstrap_org_user(client, email_prefix="conn-perm-write")
    reader = _read_only_connector_headers(
        db_session, client, org["organization_id"], "conn-reader@example.com"
    )

    listed = client.get(f"{BASE}/catalog", headers=reader)
    assert listed.status_code == 200, listed.text
    assert isinstance(listed.json(), list)

    created = client.post(
        f"{BASE}/catalog",
        headers=reader,
        json={
            "name": "Reader-attempted connector",
            "category": "sustainability",
        },
    )
    assert created.status_code == 403, created.text


def test_owner_can_create_catalog_entry(client, db_session):
    """Baseline happy path: the owner (holds connectors:write) creates a catalog
    entry successfully, confirming the 403s above are permission-specific."""
    org = bootstrap_org_user(client, email_prefix="conn-perm-owner")
    created = client.post(
        f"{BASE}/catalog",
        headers=org["org_headers"],
        json={
            "name": "Owner connector",
            "category": "sustainability",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Owner connector"
    assert "id" in body
