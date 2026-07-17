"""Coverage for the geopolitical-risk router (app/api/v1/geopolitical_risk.py).

The existing suites (test_geopolitical_risk_monitoring_t4_15.py and
test_g6_vendor_intel_signal_quality.py) heavily exercise ingest, the summary
cross-reference, staleness/unmonitored gaps, the vendor risk cascade, and
:manage 403 on ingest + create-exposure. They do NOT touch two whole endpoints:

  * DELETE /vendor-exposures/{exposure_id}
  * GET /vendor-exposures (list + filters)

and they never assert query-parameter validation on GET /signals. This file
adds:
  * DELETE happy path (204) with list reflecting the soft-delete.
  * DELETE org-scoping (cross-org exposure -> 404) and missing id -> 404.
  * DELETE RBAC: a ``readonly`` member has geopolitical_risk:read (so it can
    LIST) but lacks :manage (so DELETE -> 403).
  * GET /vendor-exposures happy path plus vendor_id / region filters.
  * GET /signals rejects out-of-range pagination params (422).
"""

from __future__ import annotations

import uuid

from tests.helpers.auth_org import add_org_member, bootstrap_org_user

BASE = "/api/v1/geopolitical-risk"


def _create_vendor(client, org: dict, *, name: str) -> str:
    r = client.post(
        "/api/v1/compliance/vendors",
        headers=org["org_headers"],
        json={"name": name, "vendor_type": "software", "owner_user_id": org["user_id"]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _create_exposure(client, org: dict, *, vendor_id: str, region: str) -> str:
    r = client.post(
        f"{BASE}/vendor-exposures",
        headers=org["org_headers"],
        json={"vendor_id": vendor_id, "region": region},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# DELETE /vendor-exposures/{id}
# ---------------------------------------------------------------------------


def test_delete_vendor_exposure_happy_path(client, db_session):
    org = bootstrap_org_user(client, email_prefix="geo-cov-del")
    vendor_id = _create_vendor(client, org, name="Deletable Vendor")
    exposure_id = _create_exposure(client, org, vendor_id=vendor_id, region="Delregion")

    # Present before delete.
    listing = client.get(f"{BASE}/vendor-exposures", headers=org["org_headers"])
    assert listing.status_code == 200
    assert any(row["id"] == exposure_id for row in listing.json())

    deleted = client.delete(f"{BASE}/vendor-exposures/{exposure_id}", headers=org["org_headers"])
    assert deleted.status_code == 204, deleted.text

    # Gone from the list after the soft delete.
    listing_after = client.get(f"{BASE}/vendor-exposures", headers=org["org_headers"])
    assert listing_after.status_code == 200
    assert all(row["id"] != exposure_id for row in listing_after.json())

    # Deleting again -> 404 (no longer resolvable).
    repeat = client.delete(f"{BASE}/vendor-exposures/{exposure_id}", headers=org["org_headers"])
    assert repeat.status_code == 404, repeat.text


def test_delete_missing_exposure_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="geo-cov-del404")
    r = client.delete(f"{BASE}/vendor-exposures/{uuid.uuid4()}", headers=org["org_headers"])
    assert r.status_code == 404, r.text


def test_delete_cross_org_exposure_returns_404(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="geo-cov-del-a")
    org_b = bootstrap_org_user(client, email_prefix="geo-cov-del-b")
    vendor_b = _create_vendor(client, org_b, name="Org B Vendor")
    exposure_b = _create_exposure(client, org_b, vendor_id=vendor_b, region="OrgBRegion")

    # Org A must not be able to delete org B's exposure.
    r = client.delete(f"{BASE}/vendor-exposures/{exposure_b}", headers=org_a["org_headers"])
    assert r.status_code == 404, r.text

    # And it is untouched for org B.
    still_there = client.get(f"{BASE}/vendor-exposures", headers=org_b["org_headers"])
    assert any(row["id"] == exposure_b for row in still_there.json())


def test_delete_requires_manage_permission(client, db_session):
    org = bootstrap_org_user(client, email_prefix="geo-cov-del-perm")
    vendor_id = _create_vendor(client, org, name="Perm Vendor")
    exposure_id = _create_exposure(client, org, vendor_id=vendor_id, region="PermRegion")

    # readonly holds geopolitical_risk:read but NOT :manage.
    readonly = add_org_member(
        db_session, client, org["organization_id"], "geo-cov-ro@example.com", role_name="readonly"
    )

    # Can read the exposure list...
    listed = client.get(f"{BASE}/vendor-exposures", headers=readonly)
    assert listed.status_code == 200, listed.text

    # ...but cannot delete it.
    forbidden = client.delete(f"{BASE}/vendor-exposures/{exposure_id}", headers=readonly)
    assert forbidden.status_code == 403, forbidden.text


# ---------------------------------------------------------------------------
# GET /vendor-exposures  (list + filters)
# ---------------------------------------------------------------------------


def test_list_vendor_exposures_filters_by_vendor_and_region(client, db_session):
    org = bootstrap_org_user(client, email_prefix="geo-cov-list")
    vendor_1 = _create_vendor(client, org, name="Vendor One")
    vendor_2 = _create_vendor(client, org, name="Vendor Two")
    _create_exposure(client, org, vendor_id=vendor_1, region="Alpha")
    _create_exposure(client, org, vendor_id=vendor_1, region="Beta")
    _create_exposure(client, org, vendor_id=vendor_2, region="Alpha")

    all_rows = client.get(f"{BASE}/vendor-exposures", headers=org["org_headers"])
    assert all_rows.status_code == 200
    assert len(all_rows.json()) == 3

    by_vendor = client.get(
        f"{BASE}/vendor-exposures", headers=org["org_headers"], params={"vendor_id": vendor_1}
    )
    assert by_vendor.status_code == 200
    body = by_vendor.json()
    assert len(body) == 2
    assert {row["region"] for row in body} == {"Alpha", "Beta"}
    assert all(row["vendor_id"] == vendor_1 for row in body)

    by_region = client.get(
        f"{BASE}/vendor-exposures", headers=org["org_headers"], params={"region": "Alpha"}
    )
    assert by_region.status_code == 200
    region_body = by_region.json()
    assert len(region_body) == 2
    assert {row["vendor_id"] for row in region_body} == {vendor_1, vendor_2}


# ---------------------------------------------------------------------------
# GET /signals  pagination bounds
# ---------------------------------------------------------------------------


def test_list_signals_rejects_out_of_range_pagination(client, db_session):
    org = bootstrap_org_user(client, email_prefix="geo-cov-signals")

    over_limit = client.get(f"{BASE}/signals", headers=org["org_headers"], params={"limit": 999})
    assert over_limit.status_code == 422, over_limit.text

    negative_skip = client.get(f"{BASE}/signals", headers=org["org_headers"], params={"skip": -1})
    assert negative_skip.status_code == 422, negative_skip.text

    # A valid, empty query still succeeds.
    ok = client.get(f"{BASE}/signals", headers=org["org_headers"], params={"limit": 50, "skip": 0})
    assert ok.status_code == 200, ok.text
    assert ok.json() == []
