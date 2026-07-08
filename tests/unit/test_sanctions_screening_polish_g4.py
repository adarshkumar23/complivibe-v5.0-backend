from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.sanctions_entity import SanctionsEntity
from app.models.sanctions_screen_result import SanctionsScreenResult
from app.satellites.tprm_intelligence.sanctions_screening import SanctionsScreeningService, WatchmanSearchResult
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SATELLITE_BASE = "/api/v1/vendors"


def _create_vendor(client, org: dict, *, name: str = "Example Vendor", website: str = "https://example.com") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": name,
            "vendor_type": "software",
            "website": website,
            "owner_user_id": org["user_id"],
            "data_access": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_sberbank_entity(db_session):
    row = SanctionsEntity(
        id="NK-SBERBANK-EUROPE-AG-G4",
        caption="Sberbank Europe AG",
        schema_type="Company",
        countries=["at"],
        datasets=["us_ofac_sdn", "eu_fsf"],
        properties={"target": True, "topics": ["sanction"], "name": ["Sberbank Europe AG"]},
    )
    db_session.add(row)
    db_session.flush()
    return row


def _unavailable_watchman(self, name: str, *, limit: int = 10) -> WatchmanSearchResult:
    return WatchmanSearchResult(available=False, matches=[], error="docker unavailable in test")


def test_g4_sanctions_result_reports_freshness(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-sanctions-fresh")
    vendor = _create_vendor(client, org, name="Blue Garden Bakery LLC", website="https://blue-garden.example")
    _seed_sberbank_entity(db_session)
    monkeypatch.setattr(SanctionsScreeningService, "_watchman_search", _unavailable_watchman)

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["is_stale"] is False
    assert body["days_since_screened"] is not None
    assert body["days_since_screened"] < 1
    assert body["name_changed_since_screening"] is False


def test_g4_sanctions_result_flags_stale_result(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-sanctions-stale")
    vendor = _create_vendor(client, org, name="Aging Screen Corp", website="https://aging.example")
    _seed_sberbank_entity(db_session)
    monkeypatch.setattr(SanctionsScreeningService, "_watchman_search", _unavailable_watchman)

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    result_id = computed.json()["id"]

    row = db_session.execute(select(SanctionsScreenResult).where(SanctionsScreenResult.id == uuid.UUID(result_id))).scalar_one()
    row.screened_at = datetime.now(UTC) - timedelta(days=10)
    db_session.commit()

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen", headers=org["org_headers"])
    assert latest.status_code == 200, latest.text
    body = latest.json()
    assert body["is_stale"] is True
    assert body["days_since_screened"] >= 9.9


def test_g4_sanctions_result_flags_vendor_renamed_since_screening(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-sanctions-rename")
    vendor = _create_vendor(client, org, name="Old Name Corp", website="https://oldname.example")
    _seed_sberbank_entity(db_session)
    monkeypatch.setattr(SanctionsScreeningService, "_watchman_search", _unavailable_watchman)

    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text

    renamed = client.patch(
        f"{VENDORS_BASE}/{vendor['id']}",
        headers=org["org_headers"],
        json={"name": "New Name Corp"},
    )
    assert renamed.status_code == 200, renamed.text

    latest = client.get(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen", headers=org["org_headers"])
    assert latest.status_code == 200, latest.text
    body = latest.json()
    assert body["name_changed_since_screening"] is True


def test_g4_sanctions_near_miss_surfaced_without_escalating(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="g4-sanctions-nearmiss")
    vendor = _create_vendor(client, org, name="Near Miss Vendor Co", website="https://nearmiss.example")

    def near_miss_watchman(self, name: str, *, limit: int = 10) -> WatchmanSearchResult:
        return WatchmanSearchResult(
            available=True,
            matches=[{"id": "near-1", "caption": "Near Miss Vndr Co", "score": 0.78, "datasets": ["test"]}],
        )

    monkeypatch.setattr(SanctionsScreeningService, "_watchman_search", near_miss_watchman)
    computed = client.post(f"{SATELLITE_BASE}/{vendor['id']}/sanctions-screen/compute", headers=org["org_headers"])
    assert computed.status_code == 201, computed.text
    body = computed.json()
    assert body["match_found"] is False
    assert body["near_miss"] is True

    vendor_after = client.get(f"{VENDORS_BASE}/{vendor['id']}", headers=org["org_headers"])
    assert vendor_after.json()["risk_tier"] == "not_assessed"
