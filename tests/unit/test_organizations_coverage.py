"""Coverage for the organizations endpoint (app/api/v1/organizations.py).

Exercises the core, non-governance surface:
  - GET  /organizations/me                 (list my orgs)
  - GET  /organizations/{organization_id}  (get org, org:read)
  - PATCH /organizations/{organization_id} (update org, org:update = owner/admin only)

Covers: happy path (list + update reflected on re-fetch), org:update permission
enforcement (readonly -> 403), and edge cases (422 validation, path/header
org-scope mismatch -> 400).
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

ME = "/api/v1/organizations/me"
BASE = "/api/v1/organizations"


def test_get_my_organizations_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="org-me")
    r = client.get(ME, headers=org["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list) and len(body) == 1
    assert body[0]["id"] == org["organization_id"]
    assert "name" in body[0] and "slug" in body[0]


def test_get_organization_by_id(client, db_session):
    org = bootstrap_org_user(client, email_prefix="org-get")
    oid = org["organization_id"]
    r = client.get(f"{BASE}/{oid}", headers=org["org_headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == oid
    assert body["is_active"] is True
    assert "sanctions_match_threshold" in body


def test_update_organization_reflected_on_refetch(client, db_session):
    org = bootstrap_org_user(client, email_prefix="org-upd")
    oid = org["organization_id"]

    upd = client.patch(
        f"{BASE}/{oid}",
        headers=org["org_headers"],
        json={
            "name": "Renamed Org LLP",
            "is_significant_data_fiduciary": True,
            "sdf_category": "large-scale",
            "sanctions_match_threshold": 0.72,
        },
    )
    assert upd.status_code == 200, upd.text
    payload = upd.json()
    assert payload["organization"]["name"] == "Renamed Org LLP"
    assert payload["organization"]["is_significant_data_fiduciary"] is True
    assert payload["organization"]["sdf_category"] == "large-scale"
    assert abs(payload["organization"]["sanctions_match_threshold"] - 0.72) < 1e-9
    assert payload["audit"]["action"] == "organization.updated"

    # re-fetch reflects the change
    refetch = client.get(f"{BASE}/{oid}", headers=org["org_headers"])
    assert refetch.status_code == 200, refetch.text
    body = refetch.json()
    assert body["name"] == "Renamed Org LLP"
    assert body["is_significant_data_fiduciary"] is True
    assert body["sdf_category"] == "large-scale"
    assert abs(body["sanctions_match_threshold"] - 0.72) < 1e-9


def test_update_organization_requires_org_update_permission(client, db_session):
    # org:update is owner/admin-only per ROLE_PERMISSION_MAP; readonly lacks it -> 403.
    org = bootstrap_org_user(client, email_prefix="org-perm")
    oid = org["organization_id"]
    ro_headers = add_org_member(
        db_session, client, oid, "org-readonly@example.com", role_name="readonly"
    )
    r = client.patch(f"{BASE}/{oid}", headers=ro_headers, json={"name": "Readonly Attempt"})
    assert r.status_code == 403, r.text

    # and the org was not mutated
    refetch = client.get(f"{BASE}/{oid}", headers=org["org_headers"])
    assert refetch.status_code == 200
    assert refetch.json()["name"] != "Readonly Attempt"


def test_update_organization_validation_422(client, db_session):
    # name has min_length=2; a 1-char name fails schema validation -> 422.
    org = bootstrap_org_user(client, email_prefix="org-422")
    oid = org["organization_id"]
    r = client.patch(f"{BASE}/{oid}", headers=org["org_headers"], json={"name": "a"})
    assert r.status_code == 422, r.text


def test_update_organization_path_header_mismatch_400(client, db_session):
    # Path organization_id must match X-Organization-ID; a foreign/mismatched id -> 400.
    org = bootstrap_org_user(client, email_prefix="org-scope")
    foreign_id = str(uuid.uuid4())
    r = client.patch(
        f"{BASE}/{foreign_id}", headers=org["org_headers"], json={"name": "Cross Org Edit"}
    )
    assert r.status_code == 400, r.text
    assert "must match" in r.json()["detail"].lower()


def test_get_organization_foreign_org_scope_400(client, db_session):
    # Org A's headers cannot read Org B by path id (path must match X-Organization-ID).
    org_a = bootstrap_org_user(client, email_prefix="org-scope-a")
    org_b = bootstrap_org_user(client, email_prefix="org-scope-b")
    r = client.get(f"{BASE}/{org_b['organization_id']}", headers=org_a["org_headers"])
    assert r.status_code == 400, r.text
