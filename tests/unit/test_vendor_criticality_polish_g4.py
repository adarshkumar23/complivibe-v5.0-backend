from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.vendor import Vendor
from app.models.vendor_criticality import VendorCriticalityProfile
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"


def _create_vendor(client, org: dict, *, name: str = "Criticality Vendor") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": org["user_id"],
            "risk_tier": "not_assessed",
            "data_access": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_g4_criticality_default_profile_flags_not_configured(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-crit-default")
    vendor = _create_vendor(client, org)

    profile = client.get(f"{VENDORS_BASE}/{vendor['id']}/criticality", headers=org["org_headers"])
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["is_default"] is True
    assert body["is_stale"] is True
    assert body["profile_age_days"] is None
    assert "no_profile_configured" in body["context_flags"]


def test_g4_criticality_fresh_profile_not_stale(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-crit-fresh")
    vendor = _create_vendor(client, org, name="Fresh Vendor")

    upsert = client.put(
        f"{VENDORS_BASE}/{vendor['id']}/criticality",
        headers=org["org_headers"],
        json={
            "revenue_dependency_pct": "10.00",
            "data_volume_tier": "low",
            "operational_criticality": "medium",
            "substitutability_score": 2,
        },
    )
    assert upsert.status_code == 200, upsert.text
    body = upsert.json()
    assert body["is_stale"] is False
    assert body["profile_age_days"] is not None
    assert body["profile_age_days"] < 1
    assert "profile_stale" not in body["context_flags"]

    fetched = client.get(f"{VENDORS_BASE}/{vendor['id']}/criticality", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["is_stale"] is False


def test_g4_criticality_old_profile_flagged_stale(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-crit-stale")
    vendor = _create_vendor(client, org, name="Aging Vendor")

    upsert = client.put(
        f"{VENDORS_BASE}/{vendor['id']}/criticality",
        headers=org["org_headers"],
        json={
            "revenue_dependency_pct": "40.00",
            "data_volume_tier": "medium",
            "operational_criticality": "high",
            "substitutability_score": 3,
        },
    )
    assert upsert.status_code == 200, upsert.text

    # Simulate the profile having been set 200 days ago and never revisited.
    profile_row = db_session.execute(
        select(VendorCriticalityProfile).where(VendorCriticalityProfile.vendor_id == uuid.UUID(vendor["id"]))
    ).scalar_one()
    profile_row.updated_at = datetime.now(UTC) - timedelta(days=200)
    db_session.commit()

    fetched = client.get(f"{VENDORS_BASE}/{vendor['id']}/criticality", headers=org["org_headers"])
    assert fetched.status_code == 200, fetched.text
    body = fetched.json()
    assert body["is_stale"] is True
    assert body["profile_age_days"] >= 199
    assert "profile_stale" in body["context_flags"]


def test_g4_criticality_rejects_archived_vendor(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g4-crit-archived")
    vendor = _create_vendor(client, org, name="Retired Vendor")

    vendor_row = db_session.execute(select(Vendor).where(Vendor.id == uuid.UUID(vendor["id"]))).scalar_one()
    vendor_row.status = "archived"
    db_session.commit()

    response = client.put(
        f"{VENDORS_BASE}/{vendor['id']}/criticality",
        headers=org["org_headers"],
        json={
            "revenue_dependency_pct": "10.00",
            "data_volume_tier": "low",
            "operational_criticality": "low",
            "substitutability_score": 1,
        },
    )
    assert response.status_code == 400
    assert "Archived vendors" in response.text
