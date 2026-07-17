"""Coverage for the auditor-portal endpoints (/audit-portal/*). Zero prior
test references.

Two auth models exist here, and both are exercised:
  * Session/RBAC-authenticated *management* endpoints (create/list/get/revoke
    invitations) gated by audit:write / audit:read + an org-admin role gate.
  * A separate *portal-token* flow (Authorization: Bearer <plaintext_token>)
    that the external auditor uses to reach /me, /controls, /evidence, /reports.

Covers: happy path (issue token -> access /me + list/get), audit:write
permission enforcement on the management side, token-scoping edges (invalid /
revoked token -> 401), and org isolation of invitation lookup (404).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

INVITATIONS = "/api/v1/audit-portal/invitations"
PORTAL_ME = "/api/v1/audit-portal/me"


def _create_engagement(client, headers, title="Portal Engagement") -> str:
    r = client.post(
        "/api/v1/compliance/audit-engagements",
        headers=headers,
        json={
            "title": title,
            "audit_type": "internal_readiness",
            "scope_framework_ids": [],
            "assigned_auditor_ids": [],
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_invitation(client, headers, engagement_id, email="ext-auditor@example.com"):
    r = client.post(
        f"{INVITATIONS}?engagement_id={engagement_id}",
        headers=headers,
        json={"auditor_email": email, "auditor_name": "Ext Auditor", "expires_in_days": 30},
    )
    return r


def _portal_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_portal_invitation_issue_and_access_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ap-happy")
    h = org["org_headers"]
    eng_id = _create_engagement(client, h, title="SOC2 Readiness")

    created = _create_invitation(client, h, eng_id, email="soc-auditor@example.com")
    assert created.status_code == 201, created.text
    inv = created.json()
    assert inv["auditor_email"] == "soc-auditor@example.com"
    assert inv["plaintext_token"]  # one-time token surfaced only on creation
    assert "once" in inv["warning"].lower()
    invitation_id = inv["invitation_id"]
    token = inv["plaintext_token"]

    # Management list/get (session/RBAC) sees the invitation, masked email, active status.
    listed = client.get(INVITATIONS, headers=h)
    assert listed.status_code == 200, listed.text
    match = [row for row in listed.json() if row["id"] == invitation_id]
    assert match and match[0]["status"] == "active"
    assert match[0]["masked_email"].endswith("@example.com") and "***" in match[0]["masked_email"]

    one = client.get(f"{INVITATIONS}/{invitation_id}", headers=h)
    assert one.status_code == 200, one.text
    assert one.json()["audit_engagement_id"] == eng_id

    # Portal-token flow: the external auditor authenticates with the plaintext token.
    me = client.get(PORTAL_ME, headers=_portal_headers(token))
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["auditor_email"] == "soc-auditor@example.com"
    assert me_body["audit_engagement_title"] == "SOC2 Readiness"
    assert me_body["access_count"] >= 1

    # Empty framework scope -> scoped resource endpoints return empty lists (still 200).
    controls = client.get("/api/v1/audit-portal/controls", headers=_portal_headers(token))
    assert controls.status_code == 200, controls.text
    assert controls.json() == []


def test_create_invitation_requires_audit_write(client, db_session):
    # readonly role has audit:read but NOT audit:write -> 403 on invitation creation.
    org = bootstrap_org_user(client, email_prefix="ap-perm")
    eng_id = _create_engagement(client, org["org_headers"])
    ro = add_org_member(db_session, client, org["organization_id"], "ap-readonly@example.com", role_name="readonly")
    r = _create_invitation(client, ro, eng_id)
    assert r.status_code == 403, r.text


def test_portal_token_invalid_and_revoked_return_401(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ap-token")
    h = org["org_headers"]
    eng_id = _create_engagement(client, h)

    # A bogus token is rejected (token-scoping: no matching hash).
    bogus = client.get(PORTAL_ME, headers=_portal_headers("not-a-real-token"))
    assert bogus.status_code == 401, bogus.text

    created = _create_invitation(client, h, eng_id, email="revoke-me@example.com")
    assert created.status_code == 201, created.text
    invitation_id = created.json()["invitation_id"]
    token = created.json()["plaintext_token"]

    # Valid before revoke.
    assert client.get(PORTAL_ME, headers=_portal_headers(token)).status_code == 200

    # Revoke via management endpoint, then the same token no longer authenticates.
    revoked = client.post(f"{INVITATIONS}/{invitation_id}/revoke", headers=h)
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "revoked"

    after = client.get(PORTAL_ME, headers=_portal_headers(token))
    assert after.status_code == 401, after.text


def test_invitation_lookup_is_org_scoped(client, db_session):
    # org A owns an invitation; org B must not be able to resolve it -> 404.
    org_a = bootstrap_org_user(client, email_prefix="ap-a")
    eng_a = _create_engagement(client, org_a["org_headers"])
    created = _create_invitation(client, org_a["org_headers"], eng_a)
    assert created.status_code == 201, created.text
    invitation_id = created.json()["invitation_id"]

    org_b = bootstrap_org_user(client, email_prefix="ap-b")
    cross = client.get(f"{INVITATIONS}/{invitation_id}", headers=org_b["org_headers"])
    assert cross.status_code == 404, cross.text

    # And a fully unknown id is likewise 404 for the owning org.
    missing = client.get(f"{INVITATIONS}/{uuid.uuid4()}", headers=org_a["org_headers"])
    assert missing.status_code == 404, missing.text
