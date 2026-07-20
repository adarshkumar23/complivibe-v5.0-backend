"""Missing authorization gates on two endpoint groups (2026-07-20).

1. /preferences/notifications (GET, PUT bulk, PUT one) authenticated the caller and
   resolved the org from X-Organization-ID, but never checked that the caller was a
   MEMBER of that org. get_current_organization only loads the row and 404s if it is
   missing. So any authenticated user could read and write notification-preference rows
   tagged to an organization they have nothing to do with.

2. POST /reports/share minted an externally-reachable share link behind
   `compliance:read`. Every system role holds compliance:read -- including auditor and
   readonly, whose entire point is that they cannot change or export anything. Minting
   a share link is data egress, not a read.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.user_notification_preference import UserNotificationPreference
from tests.helpers.auth_org import add_org_member, bootstrap_org_user

PREFS = "/api/v1/preferences/notifications"
SHARE = "/api/v1/reports/share"


def _foreign_headers(outsider: dict, victim_org_id: str) -> dict[str, str]:
    headers = dict(outsider["headers"])
    headers["X-Organization-ID"] = victim_org_id
    return headers


def test_non_member_cannot_read_another_orgs_notification_preferences(client, db_session):
    victim = bootstrap_org_user(client, email_prefix="nprefs-victim")
    outsider = bootstrap_org_user(client, email_prefix="nprefs-outsider")

    resp = client.get(PREFS, headers=_foreign_headers(outsider, victim["organization_id"]))
    assert resp.status_code == 403, resp.text

    # ...and the read must not have seeded rows into the victim org as a side effect.
    db_session.expire_all()
    rows = db_session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == UUID(victim["organization_id"]),
            UserNotificationPreference.user_id == UUID(outsider["user_id"]),
        )
    ).scalars().all()
    assert rows == []


def test_non_member_cannot_write_a_single_preference_into_another_org(client, db_session):
    victim = bootstrap_org_user(client, email_prefix="nprefs-w-victim")
    outsider = bootstrap_org_user(client, email_prefix="nprefs-w-outsider")

    resp = client.put(
        f"{PREFS}/task_assigned",
        headers=_foreign_headers(outsider, victim["organization_id"]),
        json={"channel": "email", "is_enabled": False, "min_severity": None},
    )
    assert resp.status_code == 403, resp.text

    db_session.expire_all()
    rows = db_session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == UUID(victim["organization_id"]),
            UserNotificationPreference.user_id == UUID(outsider["user_id"]),
        )
    ).scalars().all()
    assert rows == [], "a non-member must not be able to create rows tagged to this org"


def test_non_member_cannot_bulk_write_preferences_into_another_org(client, db_session):
    victim = bootstrap_org_user(client, email_prefix="nprefs-b-victim")
    outsider = bootstrap_org_user(client, email_prefix="nprefs-b-outsider")

    resp = client.put(
        f"{PREFS}/bulk",
        headers=_foreign_headers(outsider, victim["organization_id"]),
        json={"updates": [{"notification_type": "task_assigned", "channel": "none", "is_enabled": False}]},
    )
    assert resp.status_code == 403, resp.text

    db_session.expire_all()
    rows = db_session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.organization_id == UUID(victim["organization_id"]),
            UserNotificationPreference.user_id == UUID(outsider["user_id"]),
        )
    ).scalars().all()
    assert rows == []


def test_members_can_still_read_and_write_their_own_orgs_preferences(client):
    org = bootstrap_org_user(client, email_prefix="nprefs-ok")
    assert client.get(PREFS, headers=org["org_headers"]).status_code == 200
    single = client.put(
        f"{PREFS}/task_assigned",
        headers=org["org_headers"],
        json={"channel": "in_app", "is_enabled": False, "min_severity": None},
    )
    assert single.status_code == 200, single.text
    assert single.json()["channel"] == "in_app"
    bulk = client.put(
        f"{PREFS}/bulk",
        headers=org["org_headers"],
        json={"updates": [{"notification_type": "sla_breach", "channel": "none", "is_enabled": False}]},
    )
    assert bulk.status_code == 200, bulk.text


# --------------------------------------------------------------------------------
# POST /reports/share
# --------------------------------------------------------------------------------


def _share_payload() -> dict:
    return {"report_type": "compliance_summary", "report_params": {}, "expires_hours": 24}


def test_readonly_role_cannot_mint_a_report_share_link(client, db_session):
    org = bootstrap_org_user(client, email_prefix="share-ro")
    headers = add_org_member(
        db_session, client, org["organization_id"], "share-ro-user@example.com", role_name="readonly"
    )

    # Proof the role really does hold compliance:read (the old gate) -- so this test
    # fails for the right reason before the fix, not because the user lacks access.
    assert client.get("/api/v1/reports/shared-links", headers=headers).status_code == 200

    resp = client.post(SHARE, headers=headers, json=_share_payload())
    assert resp.status_code == 403, resp.text
    assert "reports:share" in resp.json()["detail"]


def test_auditor_role_cannot_mint_a_report_share_link(client, db_session):
    org = bootstrap_org_user(client, email_prefix="share-aud")
    headers = add_org_member(
        db_session, client, org["organization_id"], "share-aud-user@example.com", role_name="auditor"
    )

    assert client.get("/api/v1/reports/shared-links", headers=headers).status_code == 200
    assert client.post(SHARE, headers=headers, json=_share_payload()).status_code == 403


def test_owner_can_still_mint_a_report_share_link(client):
    org = bootstrap_org_user(client, email_prefix="share-owner")
    resp = client.post(SHARE, headers=org["org_headers"], json=_share_payload())
    assert resp.status_code == 200, resp.text
    assert resp.json()["share_url"]


def test_compliance_manager_can_still_mint_a_report_share_link(client, db_session):
    org = bootstrap_org_user(client, email_prefix="share-cm")
    headers = add_org_member(
        db_session, client, org["organization_id"], "share-cm-user@example.com", role_name="compliance_manager"
    )
    resp = client.post(SHARE, headers=headers, json=_share_payload())
    assert resp.status_code == 200, resp.text


def test_reports_share_permission_is_scoped_to_the_egress_roles(client):
    """Regression guard on the grant decision itself: reports:share belongs to the
    roles that may already change and export org data, not to the read-only postures."""
    from app.services.seed_service import PERMISSIONS, ROLE_PERMISSION_MAP

    assert "reports:share" in PERMISSIONS
    holders = {role for role, perms in ROLE_PERMISSION_MAP.items() if "reports:share" in perms}
    assert holders == {"owner", "admin", "compliance_manager"}
    for role in ("readonly", "auditor", "reviewer"):
        assert "compliance:read" in ROLE_PERMISSION_MAP[role], "premise: these roles do hold the old gate"
