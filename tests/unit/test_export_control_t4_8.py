from __future__ import annotations

import json
import uuid

from app.models.audit_log import AuditLog
from app.models.permission import Permission
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


def test_export_control_permissions_seeded(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-perms")

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "export_control:read" in keys
    assert "export_control:manage" in keys
    # must be dedicated, distinct from vendors:read/vendors:write
    assert "export_control:read" != "vendors:read"
    assert "export_control:manage" != "vendors:write"

    response = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert response.status_code == 200
    codes = set(response.json()["permission_codes"])
    assert "export_control:read" in codes
    assert "export_control:manage" in codes


def test_screen_ear99_common_destination_no_license_required(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-ear99")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Ordinary Software Vendor")

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={
            "item_description": "Standard commercial off-the-shelf laptop computer",
            "destination_country": "Canada",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["eccn"] is None
    assert body["license_required"] is False
    assert body["license_determination_basis"]
    assert "no license" in body["license_determination_basis"].lower()
    assert body["denied_party_screening_result"]["match_found"] is False


def test_screen_embargoed_destination_requires_license(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-embargo")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Embargo Destination Vendor")

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={
            "item_description": "Industrial control equipment",
            "destination_country": "Iran",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["license_required"] is True
    assert "iran" in body["license_determination_basis"].lower()
    assert "country group" in body["license_determination_basis"].lower() or "commerce country chart" in body["license_determination_basis"].lower()


def test_screen_denied_party_match_requires_license(client, db_session, tmp_path):
    org = bootstrap_org_user(client, email_prefix="ec-denied")
    vendor_name = "Denied Test Corp Ltd"
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name=vendor_name)

    fixture_path = tmp_path / "denied_parties.jsonl"
    fixture_path.write_text(
        json.dumps(
            {
                "id": "test-denied-entity-1",
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

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={
            "item_description": "General purpose components",
            "destination_country": "Germany",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["denied_party_screening_result"]["match_found"] is True
    assert body["license_required"] is True
    assert "denied-party" in body["license_determination_basis"].lower() or "denied party" in body["license_determination_basis"].lower()


def test_screen_invalid_eccn_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-badeccn")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={
            "item_description": "Some item",
            "destination_country": "France",
            "eccn": "NOTVALID",
        },
    )
    assert response.status_code == 422, response.text


def test_screen_empty_destination_country_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-emptydest")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={
            "item_description": "Some item",
            "destination_country": "   ",
        },
    )
    assert response.status_code == 422, response.text


def test_screen_empty_item_description_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-emptyitem")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={
            "item_description": "",
            "destination_country": "France",
        },
    )
    assert response.status_code == 422, response.text


def test_vendor_not_in_org_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-404")
    fake_vendor_id = uuid.uuid4()

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{fake_vendor_id}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Some item", "destination_country": "France"},
    )
    assert response.status_code == 404, response.text

    response_get = client.get(f"{EXPORT_CONTROL_BASE}/{fake_vendor_id}/export-control", headers=org["org_headers"])
    assert response_get.status_code == 404, response_get.text


def test_history_newest_first_and_latest_404_when_empty(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-history")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    latest_empty = client.get(f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control", headers=org["org_headers"])
    assert latest_empty.status_code == 404, latest_empty.text
    assert "not found" in latest_empty.json()["detail"].lower() or "no export control" in latest_empty.json()["detail"].lower()

    history_empty = client.get(f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/history", headers=org["org_headers"])
    assert history_empty.status_code == 200, history_empty.text
    assert history_empty.json() == []

    first = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "First item", "destination_country": "Canada"},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Second item", "destination_country": "Iran"},
    )
    assert second.status_code == 201, second.text

    history = client.get(f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/history", headers=org["org_headers"])
    assert history.status_code == 200, history.text
    rows = history.json()
    assert len(rows) == 2
    assert rows[0]["item_description"] == "Second item"
    assert rows[1]["item_description"] == "First item"

    latest = client.get(f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control", headers=org["org_headers"])
    assert latest.status_code == 200, latest.text
    assert latest.json()["item_description"] == "Second item"


def test_audit_log_written_for_compute(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ec-audit")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{EXPORT_CONTROL_BASE}/{vendor['id']}/export-control/screen",
        headers=org["org_headers"],
        json={"item_description": "Audited item", "destination_country": "Canada"},
    )
    assert response.status_code == 201, response.text

    logs = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "vendor.export_control_check.computed")
        .all()
    )
    assert len(logs) == 1
    assert str(logs[0].organization_id) == org["organization_id"]
