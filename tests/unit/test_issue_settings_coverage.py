"""Coverage for the org issue-settings singleton endpoint
(/compliance/issue-settings). Zero prior test references.

Covers GET default-provisioning + PATCH happy path, issues:read / issues:admin
permission enforcement, and per-org isolation of the singleton.
"""

from __future__ import annotations

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/compliance/issue-settings"


def test_issue_settings_get_and_update_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="iset-happy")
    h, oid = org["org_headers"], org["organization_id"]

    # GET auto-provisions the singleton with the default require_rca_before_close=True.
    got = client.get(BASE, headers=h)
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["organization_id"] == oid
    assert body["require_rca_before_close"] is True
    assert "id" in body and "created_at" in body and "updated_at" in body

    # PATCH flips the flag and echoes the new value.
    patched = client.patch(BASE, headers=h, json={"require_rca_before_close": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["require_rca_before_close"] is False
    assert patched.json()["id"] == body["id"]  # same singleton row

    # GET reflects the persisted change.
    again = client.get(BASE, headers=h)
    assert again.status_code == 200, again.text
    assert again.json()["require_rca_before_close"] is False


def test_issue_settings_get_requires_issues_read(client, db_session):
    # auditor role lacks issues:read -> 403.
    org = bootstrap_org_user(client, email_prefix="iset-getperm")
    auditor = add_org_member(db_session, client, org["organization_id"], "iset-auditor@example.com", role_name="auditor")
    r = client.get(BASE, headers=auditor)
    assert r.status_code == 403, r.text


def test_issue_settings_update_requires_issues_admin(client, db_session):
    # readonly role has issues:read but NOT issues:admin -> can GET but 403 on PATCH.
    org = bootstrap_org_user(client, email_prefix="iset-updperm")
    ro = add_org_member(db_session, client, org["organization_id"], "iset-readonly@example.com", role_name="readonly")
    assert client.get(BASE, headers=ro).status_code == 200
    r = client.patch(BASE, headers=ro, json={"require_rca_before_close": False})
    assert r.status_code == 403, r.text


def test_issue_settings_org_scoped(client, db_session):
    # org A flips its flag to False; org B's independent singleton stays at the default.
    org_a = bootstrap_org_user(client, email_prefix="iset-a")
    a_patch = client.patch(BASE, headers=org_a["org_headers"], json={"require_rca_before_close": False})
    assert a_patch.status_code == 200, a_patch.text
    assert a_patch.json()["require_rca_before_close"] is False

    org_b = bootstrap_org_user(client, email_prefix="iset-b")
    b_get = client.get(BASE, headers=org_b["org_headers"])
    assert b_get.status_code == 200, b_get.text
    assert b_get.json()["organization_id"] == org_b["organization_id"]
    assert b_get.json()["require_rca_before_close"] is True
