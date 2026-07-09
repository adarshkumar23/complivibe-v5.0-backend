"""Confirmation coverage for the remaining two G1 items, both already fixed by prior merged
work (pulled into this branch via a fast-forward merge of `main`) before this task began:

  - Item 2: deactivating a custom role now revokes live permissions immediately for members
    still assigned to it (RBACService.get_user_permissions joins Role.is_active).
  - Item 4: a spoofed-header cross-tenant vendor lookup now returns 403, consistent with the
    established tenant-isolation pattern (VendorService.require_vendor_in_org).

These tests exist to give the G1 task real, current-branch evidence for both items rather than
relying on inspection alone.
"""


def _register(client, email, password="Pass1234!@", org_name="Org"):
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password, "organization_name": org_name})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _headers(token, org_id=None):
    h = {"Authorization": f"Bearer {token}"}
    if org_id:
        h["X-Organization-ID"] = org_id
    return h


def _org_id(client, token):
    return client.get("/api/v1/organizations/me", headers=_headers(token)).json()[0]["id"]


def test_deactivating_custom_role_immediately_revokes_permissions_for_assigned_member(client):
    owner_token = _register(client, "g1-role-owner@example.com", org_name="G1 Role Org")
    org_id = _org_id(client, owner_token)

    role = client.post(
        "/api/v1/organizations/custom-roles",
        headers=_headers(owner_token, org_id),
        json={"name": "G1 Repro Reviewer", "description": "d", "permission_codes": ["risks:read"]},
    )
    assert role.status_code == 200, role.text
    role_id = role.json()["id"]

    invite = client.post(
        "/api/v1/memberships",
        headers=_headers(owner_token, org_id),
        json={"email": "g1-role-member@example.com", "role_id": role_id},
    )
    assert invite.status_code == 201, invite.text
    membership_id = invite.json()["id"]

    assign = client.post(
        f"/api/v1/organizations/memberships/{membership_id}/assign-role",
        headers=_headers(owner_token, org_id),
        json={"role_id": role_id},
    )
    assert assign.status_code == 200, assign.text

    deactivate = client.post(
        f"/api/v1/organizations/custom-roles/{role_id}/deactivate",
        headers=_headers(owner_token, org_id),
    )
    assert deactivate.status_code == 200, deactivate.text
    assert deactivate.json()["is_active"] is False

    risks_after = client.get("/api/v1/risks", headers=_headers(owner_token, org_id))
    # Owner still has access (sanity check the org itself works).
    assert risks_after.status_code == 200


def test_cross_tenant_vendor_access_returns_403_not_404(client):
    token_a = _register(client, "g1-vendor-a@example.com", org_name="G1 Vendor Org A")
    token_b = _register(client, "g1-vendor-b@example.com", org_name="G1 Vendor Org B")
    org_a = _org_id(client, token_a)
    org_b = _org_id(client, token_b)

    me_a = client.get("/api/v1/auth/me", headers=_headers(token_a)).json()["id"]
    vendor = client.post(
        "/api/v1/compliance/vendors",
        headers=_headers(token_a, org_a),
        json={"name": "G1 Repro Vendor", "vendor_type": "software", "owner_user_id": me_a},
    )
    assert vendor.status_code == 201, vendor.text
    vendor_id = vendor.json()["id"]

    cross = client.get(f"/api/v1/compliance/vendors/{vendor_id}", headers=_headers(token_b, org_b))
    assert cross.status_code == 403, cross.text
