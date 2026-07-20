"""Regression: SCIM provision_user cross-tenant mutation (2026-07-20).

Before the fix, SCIMService.provision_user resolved the existing user by a GLOBAL email
lookup with no org filter (scim_service.py:90). Because User is a shared global identity,
a SCIM token from org A could POST /scim/v2/Users with the email of a user belonging to
org B and (a) create a membership binding that user into org A (absorb), (b) overwrite
the user's global full_name (rename), and (c) via the asymmetric _set_membership_active,
flip the user's global is_active back to active (reactivate) -- overriding a
deactivation org B had performed.

The fix scopes the lookup to the caller's org, refuses to touch a user that exists only
in another org, and makes the active-state recompute symmetric.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.membership import Membership
from app.models.user import User
from tests.helpers.auth_org import bootstrap_org_user

SCIM_USERS = "/api/v1/scim/v2/Users"


def _enable_scim(db_session, org_id: str) -> None:
    from app.models.organization import Organization

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


def test_scim_token_cannot_absorb_reactivate_or_rename_another_orgs_user(client, db_session):
    victim_email = "victim@example.com"

    # --- Org B: provision the victim, then deactivate them (org B's own decision). ---
    org_b = bootstrap_org_user(client, email_prefix="scim-xt-b")
    _enable_scim(db_session, org_b["organization_id"])
    token_b = _scim_token(client, org_b["org_headers"], "B token")
    created = client.post(
        SCIM_USERS,
        headers=_bearer(token_b),
        json={"userName": victim_email, "name": {"givenName": "Real", "familyName": "Victim"}, "active": True},
    )
    assert created.status_code in (200, 201), created.text
    victim_id = created.json()["id"]
    assert client.delete(f"{SCIM_USERS}/{victim_id}", headers=_bearer(token_b)).status_code == 204

    db_session.expire_all()
    victim = db_session.get(User, UUID(victim_id))
    assert victim.is_active is False  # deactivated by org B; only member of org B
    assert victim.full_name == "Real Victim"

    # --- Org A: attacker with its own valid SCIM token. ---
    org_a = bootstrap_org_user(client, email_prefix="scim-xt-a")
    _enable_scim(db_session, org_a["organization_id"])
    token_a = _scim_token(client, org_a["org_headers"], "A token")

    # The attack: provision the victim's email from org A, trying to reactivate + rename.
    attack = client.post(
        SCIM_USERS,
        headers=_bearer(token_a),
        json={"userName": victim_email, "name": {"givenName": "Evil", "familyName": "Rename"}, "active": True},
    )
    assert attack.status_code == 409, attack.text  # refused -- cannot touch another org's user

    db_session.expire_all()
    victim = db_session.get(User, UUID(victim_id))
    # NOT reactivated:
    assert victim.is_active is False
    assert victim.status == "inactive"
    # NOT renamed:
    assert victim.full_name == "Real Victim"
    # NOT absorbed into org A:
    membership_a = db_session.execute(
        select(Membership).where(
            Membership.user_id == UUID(victim_id),
            Membership.organization_id == UUID(org_a["organization_id"]),
        )
    ).scalar_one_or_none()
    assert membership_a is None


def test_scim_same_org_provisioning_still_works(client, db_session):
    """No over-correction: an org can still create, re-provision (rename/reactivate), and
    manage its OWN users."""
    org = bootstrap_org_user(client, email_prefix="scim-xt-own")
    _enable_scim(db_session, org["organization_id"])
    token = _scim_token(client, org["org_headers"], "own token")

    created = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "own-user@example.com", "name": {"givenName": "First", "familyName": "Last"}, "active": True},
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["id"]

    # Re-provision the same (own) user: rename + it stays a single user in this org.
    again = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "own-user@example.com", "name": {"givenName": "Renamed", "familyName": "Same"}, "active": True},
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == user_id
    db_session.expire_all()
    assert db_session.get(User, UUID(user_id)).full_name == "Renamed Same"

    # A genuinely new email is created fresh.
    fresh = client.post(
        SCIM_USERS,
        headers=_bearer(token),
        json={"userName": "brand-new@example.com", "name": {"givenName": "Brand", "familyName": "New"}, "active": True},
    )
    assert fresh.status_code == 201, fresh.text
