"""Audit coverage for SCIM provision_user's non-create paths (2026-07-20).

`deprovision_user` has always been audited, and so has the create branch of
`provision_user`. The two remaining branches were silent:

  1. The existing-member branch -- a SCIM POST for a user who is already a member
     activates/deactivates their membership and can rename them. That is an
     identity-lifecycle mutation driven by an external IdP with no interactive
     actor, so it is exactly the kind of change that must be reconstructible.
  2. The cross-tenant 409 reject -- an IdP token for org A asking to provision a
     user that belongs to org B. That is a tenant-boundary probe. Returning 409
     and forgetting it means the attempt never reaches anyone who could notice a
     pattern of them.

These tests pin both.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.organization import Organization
from tests.helpers.auth_org import bootstrap_org_user

SCIM_USERS = "/api/v1/scim/v2/Users"


def _enable_scim(db_session, org_id: str) -> None:
    org = db_session.get(Organization, UUID(org_id))
    org.subscription_status = "active"
    org.subscription_plan = "enterprise"
    db_session.commit()


def _scim_token(client, org_headers: dict[str, str], description: str) -> str:
    resp = client.post("/api/v1/scim-tokens", headers=org_headers, json={"description": description})
    assert resp.status_code == 201, resp.text
    return resp.json()["raw_token"]


def _bearer(raw_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_token}"}


def _actions(db_session, org_id: str, prefix: str = "user.") -> list[AuditLog]:
    rows = db_session.execute(
        select(AuditLog)
        .where(AuditLog.organization_id == UUID(org_id), AuditLog.entity_type == "users")
        .order_by(AuditLog.created_at.asc())
    ).scalars().all()
    return [r for r in rows if r.action.startswith(prefix)]


def _scim_org(client, db_session, prefix: str) -> tuple[dict, str]:
    org = bootstrap_org_user(client, email_prefix=prefix)
    _enable_scim(db_session, org["organization_id"])
    return org, _scim_token(client, org["org_headers"], f"{prefix} token")


def test_scim_reactivation_of_an_existing_member_is_audited(client, db_session):
    org, token = _scim_org(client, db_session, "scim-audit-react")
    created = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "member@example.com", "name": {"givenName": "Mem", "familyName": "Ber"}, "active": True},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]
    assert client.delete(f"{SCIM_USERS}/{user_id}", headers=_bearer(token)).status_code == 204

    # Re-POST the same userName: the existing-member branch, reactivating them.
    again = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "member@example.com", "name": {"givenName": "Mem", "familyName": "Ber"}, "active": True},
    )
    assert again.status_code == 200, again.text

    db_session.expire_all()
    rows = _actions(db_session, org["organization_id"])
    updates = [r for r in rows if r.action == "user.reprovisioned_via_scim"]
    assert len(updates) == 1, f"existing-member SCIM provision must be audited; saw {[r.action for r in rows]}"
    row = updates[0]
    assert row.entity_id == UUID(user_id)
    assert row.metadata_json["source"] == "scim"
    assert row.before_json["active"] is False
    assert row.after_json["active"] is True


def test_scim_rename_of_an_existing_member_is_audited(client, db_session):
    org, token = _scim_org(client, db_session, "scim-audit-rename")
    created = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "renamed@example.com", "name": {"givenName": "Old", "familyName": "Name"}, "active": True},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    renamed = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "renamed@example.com", "name": {"givenName": "New", "familyName": "Name"}, "active": True},
    )
    assert renamed.status_code == 200, renamed.text

    db_session.expire_all()
    updates = [r for r in _actions(db_session, org["organization_id"]) if r.action == "user.reprovisioned_via_scim"]
    assert len(updates) == 1, "a SCIM rename of an existing member must be audited"
    row = updates[0]
    assert row.entity_id == UUID(user_id)
    assert row.before_json["full_name"] == "Old Name"
    assert row.after_json["full_name"] == "New Name"


def test_cross_tenant_provision_reject_is_recorded_as_a_security_event(client, db_session):
    """The 409 itself is the finding. It must survive the failed request."""
    org_b, token_b = _scim_org(client, db_session, "scim-audit-victim")
    victim = client.post(
        SCIM_USERS,
        headers=_bearer(token_b),
        json={"userName": "crossvictim@example.com", "name": {"givenName": "Cross", "familyName": "Victim"}},
    )
    assert victim.status_code == 201, victim.text

    org_a, token_a = _scim_org(client, db_session, "scim-audit-attacker")
    rejected = client.post(
        SCIM_USERS,
        headers=_bearer(token_a),
        json={"userName": "crossvictim@example.com", "name": {"givenName": "Stolen", "familyName": "Identity"}},
    )
    assert rejected.status_code == 409, rejected.text

    db_session.expire_all()
    # Recorded against the ATTEMPTING org -- that is whose token misbehaved.
    rows = _actions(db_session, org_a["organization_id"], prefix="user.scim_cross_tenant")
    assert len(rows) == 1, "the cross-tenant SCIM reject must be recorded, not just returned as HTTP 409"
    row = rows[0]
    assert row.action == "user.scim_cross_tenant_provision_rejected"
    assert row.organization_id == UUID(org_a["organization_id"])
    assert row.metadata_json["source"] == "scim"
    assert row.metadata_json["attempted_email"] == "crossvictim@example.com"
    # No entity_id: the target user is deliberately not resolved for the caller's org.
    assert row.entity_id is None

    # And nothing was written into the victim org's trail by the attacker.
    assert _actions(db_session, org_b["organization_id"], prefix="user.scim_cross_tenant") == []
