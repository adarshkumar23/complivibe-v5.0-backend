"""Deepened coverage for the non-human-identities router
(app/api/v1/non_human_identities.py).

Existing tests (test_non_human_identities_t41, test_g2_nhi_orphan_offboarding_wiring)
cover CRUD + summary + orphan-scan happy paths, a cross-org 404 on GET, and the
offboarding->orphan wiring. This file adds the gaps they leave:

  * permission enforcement -- identity_governance:read on the read endpoints
    (403 for a bespoke zero-permission persona, since every seeded role holds
    :read) and identity_governance:manage on the mutating endpoints (403 for
    auditor, which lacks :manage but holds :read).
  * an authorized read persona (readonly) getting 200 through the :read gate.
  * the owner-must-be-an-active-member business rule (400).
  * the "new identity cannot start deleted" and "use delete endpoint to soft
    delete" status rules (400).
  * 404 on GET for an unknown identity id in the caller's own org.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.api.v1.non_human_identities import router as non_human_identity_router
from app.models.role import Role
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/non-human-identities"


def _ensure_router(app) -> None:
    if not any(getattr(route, "path", "") == BASE for route in app.routes):
        app.include_router(non_human_identity_router, prefix="/api/v1")


def _create_payload(owner_user_id: str, **overrides) -> dict:
    payload = {
        "name": "svc-cov",
        "identity_type": "service_account",
        "owner_user_id": owner_user_id,
        "permissions_scope": "read:controls",
        "environment": "prod",
        "last_used_at": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
    }
    payload.update(overrides)
    return payload


def _zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """A custom role holding no permissions -- the only way to hit the :read 403,
    since every seeded role holds identity_governance:read."""
    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"nhi-zero-{uuid.uuid4().hex[:8]}",
        description="no permissions",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


def test_reads_require_identity_governance_read(client, db_session, _test_app):
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-read")
    no_perms = _zero_permission_headers(db_session, client, org["organization_id"], "nhi-cov-noperm@example.com")

    assert client.get(BASE, headers=no_perms).status_code == 403
    assert client.get(f"{BASE}/summary", headers=no_perms).status_code == 403


def test_readonly_role_can_read_inventory(client, db_session, _test_app):
    # readonly holds identity_governance:read but not :manage -> reads succeed (200).
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-ro")
    readonly = add_org_member(db_session, client, org["organization_id"], "nhi-cov-ro@example.com", role_name="readonly")

    listed = client.get(BASE, headers=readonly)
    assert listed.status_code == 200, listed.text
    assert listed.json() == []
    summary = client.get(f"{BASE}/summary", headers=readonly)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total_identities"] == 0


def test_mutations_require_identity_governance_manage(client, db_session, _test_app):
    # auditor holds :read but lacks :manage -> create/update/delete/flag are 403.
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-manage")
    auditor = add_org_member(db_session, client, org["organization_id"], "nhi-cov-auditor@example.com", role_name="auditor")
    iid = uuid.uuid4()

    assert client.post(BASE, headers=auditor, json=_create_payload(org["user_id"])).status_code == 403
    assert client.patch(f"{BASE}/{iid}", headers=auditor, json={"risk_level": "high"}).status_code == 403
    assert client.delete(f"{BASE}/{iid}", headers=auditor).status_code == 403
    assert client.post(f"{BASE}/flag-orphaned", headers=auditor).status_code == 403


def test_create_rejects_non_member_owner(client, db_session, _test_app):
    # owner_user_id must resolve to an active member of the org (400).
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-owner")
    stranger_id = str(uuid.uuid4())

    resp = client.post(BASE, headers=org["org_headers"], json=_create_payload(stranger_id))
    assert resp.status_code == 400, resp.text
    assert "active member" in resp.json()["detail"]


def test_create_cannot_start_deleted(client, db_session, _test_app):
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-startdel")

    resp = client.post(BASE, headers=org["org_headers"], json=_create_payload(org["user_id"], status="deleted"))
    assert resp.status_code == 400, resp.text
    assert "cannot start as deleted" in resp.json()["detail"]


def test_update_cannot_soft_delete_via_status(client, db_session, _test_app):
    # PATCH status=deleted must be routed through the DELETE endpoint (400).
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-patchdel")
    created = client.post(BASE, headers=org["org_headers"], json=_create_payload(org["user_id"]))
    assert created.status_code == 201, created.text

    resp = client.patch(f"{BASE}/{created.json()['id']}", headers=org["org_headers"], json={"status": "deleted"})
    assert resp.status_code == 400, resp.text
    assert "delete endpoint" in resp.json()["detail"]


def test_get_unknown_identity_returns_404(client, db_session, _test_app):
    _ensure_router(_test_app)
    org = bootstrap_org_user(client, email_prefix="nhi-cov-404")
    resp = client.get(f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"])
    assert resp.status_code == 404, resp.text
