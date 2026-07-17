"""Additional coverage for the legal-matters router (app/api/v1/legal_matters.py).

The existing suite (test_legal_matter_management_t4_10.py) exercises the happy
path, status/close business rules, escalation detection and cross-org LINK
protection -- but it grants the two permission codes only to the org "owner"
role and never asserts the require_permission gate itself, nor the plain
not-found (404) responses. This file adds:

  * permission enforcement -- legal_matters:write is denied to a read-only role
    (403 on create) while legal_matters:read still lets that role GET (2xx);
    a bespoke zero-permission role is denied read (403 on list).
  * not-found edges -- GET / PATCH / status / close against an unknown matter id.
  * list filtering by status and matter_type (org-scoped happy path).

Unlike the sibling suite these tests rely on the real seeded RBAC map
(seed_service.ROLE_PERMISSION_MAP), where owner/admin/compliance_manager hold
legal_matters:write and every seeded role holds legal_matters:read.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/legal-matters"


def _zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """A member on a custom role that holds NO permissions.

    Every seeded role holds legal_matters:read, so a bespoke empty role is the
    only way to exercise the read (403) path.
    """
    from app.models.role import Role

    role = Role(
        organization_id=uuid.UUID(organization_id),
        name=f"zero-perms-{uuid.uuid4().hex[:8]}",
        description="no permissions",
        is_system=False,
        is_system_role=False,
        is_active=True,
    )
    db_session.add(role)
    db_session.commit()
    return add_org_member(db_session, client, organization_id, email, role_name=role.name)


# --------------------------------------------------------------------------
# Permission enforcement
# --------------------------------------------------------------------------
def test_create_requires_legal_matters_write(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lmc-write-perm")
    # readonly holds legal_matters:read but NOT legal_matters:write.
    ro = add_org_member(db_session, client, org["organization_id"], "lmc-ro@example.com", role_name="readonly")
    resp = client.post(BASE, headers=ro, json={"title": "Unauthorized matter"})
    assert resp.status_code == 403, resp.text


def test_readonly_role_can_read_but_not_write(client, db_session):
    """The SAME read-only member that is refused write (above) is allowed read,
    proving the 403 is the write-permission gate and not a blanket auth failure."""
    org = bootstrap_org_user(client, email_prefix="lmc-read-2xx")
    created = client.post(BASE, headers=org["org_headers"], json={"title": "Owner-created matter"})
    assert created.status_code == 201, created.text
    matter_id = created.json()["id"]

    ro = add_org_member(db_session, client, org["organization_id"], "lmc-ro2@example.com", role_name="readonly")
    listed = client.get(BASE, headers=ro)
    assert listed.status_code == 200, listed.text
    assert any(row["id"] == matter_id for row in listed.json())

    fetched = client.get(f"{BASE}/{matter_id}", headers=ro)
    assert fetched.status_code == 200, fetched.text


def test_list_requires_legal_matters_read(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lmc-read-perm")
    no_perms = _zero_permission_headers(db_session, client, org["organization_id"], "lmc-noperm@example.com")
    resp = client.get(BASE, headers=no_perms)
    assert resp.status_code == 403, resp.text


# --------------------------------------------------------------------------
# Not-found edges
# --------------------------------------------------------------------------
def test_get_unknown_matter_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lmc-404-get")
    resp = client.get(f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"])
    assert resp.status_code == 404, resp.text


def test_patch_unknown_matter_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lmc-404-patch")
    resp = client.patch(
        f"{BASE}/{uuid.uuid4()}", headers=org["org_headers"], json={"outside_counsel": "Nobody LLP"}
    )
    assert resp.status_code == 404, resp.text


def test_status_and_close_on_unknown_matter_return_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lmc-404-transitions")
    unknown = uuid.uuid4()
    status_resp = client.post(
        f"{BASE}/{unknown}/status", headers=org["org_headers"], json={"new_status": "in_progress"}
    )
    assert status_resp.status_code == 404, status_resp.text

    close_resp = client.post(f"{BASE}/{unknown}/close", headers=org["org_headers"], json={"confirm": True})
    assert close_resp.status_code == 404, close_resp.text


# --------------------------------------------------------------------------
# List filtering (org-scoped happy path)
# --------------------------------------------------------------------------
def test_list_filters_by_status_and_matter_type(client, db_session):
    org = bootstrap_org_user(client, email_prefix="lmc-filter")
    h = org["org_headers"]

    litigation = client.post(BASE, headers=h, json={"title": "Litigation A", "matter_type": "litigation"})
    assert litigation.status_code == 201, litigation.text
    litigation_id = litigation.json()["id"]

    contract = client.post(BASE, headers=h, json={"title": "Contract B", "matter_type": "contract_dispute"})
    assert contract.status_code == 201, contract.text
    contract_id = contract.json()["id"]

    # Close the contract matter so status filtering has two distinct buckets.
    closed = client.post(f"{BASE}/{contract_id}/close", headers=h, json={"confirm": True})
    assert closed.status_code == 200, closed.text

    by_type = client.get(f"{BASE}?matter_type=litigation", headers=h)
    assert by_type.status_code == 200, by_type.text
    ids = {row["id"] for row in by_type.json()}
    assert litigation_id in ids
    assert contract_id not in ids

    open_only = client.get(f"{BASE}?status=open", headers=h)
    assert open_only.status_code == 200, open_only.text
    open_ids = {row["id"] for row in open_only.json()}
    assert litigation_id in open_ids
    assert contract_id not in open_ids

    closed_only = client.get(f"{BASE}?status=closed", headers=h)
    assert closed_only.status_code == 200, closed_only.text
    closed_ids = {row["id"] for row in closed_only.json()}
    assert contract_id in closed_ids
    assert litigation_id not in closed_ids
