"""Additional coverage for the IP/licensing registry endpoints
(/ip-assets). Complements test_ip_licensing_registry_t4_11.py (which covers
CRUD happy path, expiring-soon ranking, the window setting, cross-org AI-system
link 404, invalid asset_type 422, and audit rows).

NEW here (not covered there): permission enforcement (manage vs read, incl. a
bespoke zero-permission persona since every seeded role holds ip_assets:read),
the terms.license_id taxonomy business rule (422 on unknown + canonical
case-normalization), the settings window bounds (422), and org-scoping of the
list/get endpoints.
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/ip-assets"


def _create_asset(client, headers, **overrides) -> dict:
    payload = {"name": "Model License A", "asset_type": "model_license"}
    payload.update(overrides)
    r = client.post(BASE, headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _make_zero_permission_headers(db_session, client, organization_id: str, email: str) -> dict[str, str]:
    """Create a custom role with NO permissions and a member on it.

    Every seeded role (owner/admin/compliance_manager/reviewer/auditor/readonly)
    holds ip_assets:read, so a bespoke empty role is the only way to exercise
    the 403 path on the read endpoints.
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


# -- permission enforcement -----------------------------------------------------


def test_read_endpoints_require_ip_assets_read(client, db_session):
    # A zero-permission persona is rejected from every read surface.
    org = bootstrap_org_user(client, email_prefix="ipa-cov-read")
    no_perms = _make_zero_permission_headers(db_session, client, org["organization_id"], "ipa-noperm@example.com")
    for path in (BASE, f"{BASE}/expiring-soon", f"{BASE}/settings", f"{BASE}/{uuid.uuid4()}"):
        r = client.get(path, headers=no_perms)
        assert r.status_code == 403, (path, r.text)


def test_write_endpoints_require_ip_assets_manage(client, db_session):
    # readonly holds ip_assets:read but NOT ip_assets:manage -> can read, cannot write.
    org = bootstrap_org_user(client, email_prefix="ipa-cov-manage")
    owner = org["org_headers"]
    asset = _create_asset(client, owner, name="Owned Asset")

    readonly = add_org_member(db_session, client, org["organization_id"], "ipa-ro@example.com", role_name="readonly")

    # read is allowed
    assert client.get(BASE, headers=readonly).status_code == 200
    # every mutating surface is forbidden
    assert client.post(BASE, headers=readonly, json={"name": "X", "asset_type": "patent"}).status_code == 403
    assert client.patch(f"{BASE}/{asset['id']}", headers=readonly, json={"licensee": "Y"}).status_code == 403
    assert client.delete(f"{BASE}/{asset['id']}", headers=readonly).status_code == 403
    assert client.patch(f"{BASE}/settings", headers=readonly, json={"expiring_soon_window_days": 30}).status_code == 403


# -- terms.license_id taxonomy business rule ------------------------------------


def test_unknown_license_id_rejected_but_known_id_normalized(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-cov-lic")
    headers = org["org_headers"]

    # An unrecognized license identifier is rejected rather than stored as freeform text.
    bad = client.post(
        BASE,
        headers=headers,
        json={"name": "Bad Lic", "asset_type": "model_license", "terms": {"license_id": "totally-made-up-9000"}},
    )
    assert bad.status_code == 422, bad.text
    assert "not a recognized" in str(bad.json())

    # A known identifier supplied in the wrong case is normalized to canonical casing.
    ok = _create_asset(
        client,
        headers,
        name="MIT-licensed model",
        terms={"license_id": "mit", "seats": 5},
    )
    assert ok["terms"]["license_id"] == "MIT"
    assert ok["terms"]["seats"] == 5

    # The non-OSS fallback bucket is accepted (also case-insensitively).
    prop = _create_asset(
        client,
        headers,
        name="Vendor contract",
        terms={"license_id": "proprietary"},
    )
    assert prop["terms"]["license_id"] == "Proprietary"


# -- settings window bounds -----------------------------------------------------


def test_settings_window_bounds_enforced(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ipa-cov-win")
    headers = org["org_headers"]

    # gt=0 -> zero / negative rejected
    assert client.patch(f"{BASE}/settings", headers=headers, json={"expiring_soon_window_days": 0}).status_code == 422
    assert client.patch(f"{BASE}/settings", headers=headers, json={"expiring_soon_window_days": -5}).status_code == 422
    # le=3650 -> over the ceiling rejected
    assert client.patch(f"{BASE}/settings", headers=headers, json={"expiring_soon_window_days": 3651}).status_code == 422
    # a value on the boundary is accepted
    ok = client.patch(f"{BASE}/settings", headers=headers, json={"expiring_soon_window_days": 3650})
    assert ok.status_code == 200
    assert ok.json()["expiring_soon_window_days"] == 3650


# -- org scoping ----------------------------------------------------------------


def test_ip_assets_org_scoped(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ipa-cov-a")
    org_b = bootstrap_org_user(client, email_prefix="ipa-cov-b")
    asset_a = _create_asset(client, org_a["org_headers"], name="Org A Asset")

    # org B's list does not include org A's asset
    listed_b = client.get(BASE, headers=org_b["org_headers"])
    assert listed_b.status_code == 200
    assert all(item["id"] != asset_a["id"] for item in listed_b.json())

    # org B cannot fetch org A's asset by id -> 404 (not 403), i.e. scoped-out, not just unauthorized
    fetched = client.get(f"{BASE}/{asset_a['id']}", headers=org_b["org_headers"])
    assert fetched.status_code == 404, fetched.text
