from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.satellites.tprm_intelligence.export_control_screening import ExportControlScreeningService
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
EXPORT_CONTROL_BASE = "/api/v1/vendors"


def _create_vendor(client, headers: dict[str, str], owner_user_id: str, *, name: str = "Acme Third Party") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": "not_assessed",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_clean_screen_auto_clears_status(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-polish-clear")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Clean Vendor")

    resp = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Office chairs", "destination_country": "Canada"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "cleared"
    assert any("preliminary_screening_requires_legal_confirmation" in f for f in body["context_flags"])


def test_embargoed_destination_auto_sets_license_pending(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-polish-pending")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Embargo Vendor")

    resp = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Industrial equipment", "destination_country": "Iran"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "license_pending"


def test_denied_party_match_auto_blocks_and_flags_review(client, db_session, tmp_path):
    org = bootstrap_org_user(client, email_prefix="ec-polish-blocked")
    vendor_name = "Blocked Test Corp Ltd"
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name=vendor_name)

    fixture_path = tmp_path / "denied_parties.jsonl"
    fixture_path.write_text(
        json.dumps(
            {
                "id": "test-blocked-entity-1",
                "caption": vendor_name,
                "schema": "Organization",
                "target": True,
                "datasets": ["us_trade_csl_test_fixture"],
                "properties": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ExportControlScreeningService(db_session).refresh_from_file(fixture_path)
    db_session.commit()

    resp = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "General components", "destination_country": "Germany"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "blocked"
    assert any("blocked_pending_legal_review" in f for f in body["context_flags"])


def test_status_change_between_checks_is_flagged(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-polish-drift")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Drifting Vendor")

    first = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Office supplies", "destination_country": "Canada"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "cleared"

    second = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Industrial equipment", "destination_country": "Iran"},
    )
    assert second.status_code == 201, second.text
    body = second.json()
    assert body["status"] == "license_pending"
    assert any("status_changed_from_previous_check" in f for f in body["context_flags"])


def test_dataset_updated_since_screening_is_flagged_stale(client, db_session, tmp_path):
    org = bootstrap_org_user(client, email_prefix="ec-polish-stale-dataset")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Stale Dataset Vendor")

    resp = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Office chairs", "destination_country": "Canada"},
    )
    assert resp.status_code == 201, resp.text
    check_id = resp.json()["id"]

    from app.models.export_control_check import ExportControlCheck
    import uuid as uuid_module

    db_check = db_session.get(ExportControlCheck, uuid_module.UUID(check_id))
    db_check.computed_at = datetime.now(timezone.utc) - timedelta(days=2)
    db_session.commit()

    # Simulate a denied-party dataset refresh happening after the screening ran.
    fixture_path = tmp_path / "later_refresh.jsonl"
    fixture_path.write_text(
        json.dumps(
            {
                "id": "test-later-entity-1",
                "caption": "Some Unrelated Entity",
                "schema": "Organization",
                "target": True,
                "datasets": ["us_trade_csl_test_fixture"],
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "properties": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ExportControlScreeningService(db_session).refresh_from_file(fixture_path)
    db_session.commit()

    detail = client.get(f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control", headers=org["org_headers"])
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["denied_party_dataset_stale"] is True
    assert any("denied_party_dataset_updated_since_screening" in f for f in body["context_flags"])
