from __future__ import annotations

from app.models.permission import Permission
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
BRIBERY_BASE = "/api/v1/vendors"


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


def test_anti_bribery_permissions_seeded(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-perms")

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "anti_bribery:read" in keys
    assert "anti_bribery:manage" in keys

    response = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert response.status_code == 200
    codes = set(response.json()["permission_codes"])
    assert "anti_bribery:read" in codes
    assert "anti_bribery:manage" in codes


def test_compute_high_risk_low_cpi_direct_pep_above_threshold_gift(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-high")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="High Risk Vendor")

    response = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Corruptistan",
            "jurisdiction_cpi_score": 15,
            "pep_exposure": "direct",
            "gift_hospitality_log": [
                {"date": "2026-01-01", "description": "Luxury gift", "value_usd": 5000.0},
            ],
            "industry_category": "defense",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["risk_tier"] == "high"
    assert 0.0 <= body["risk_score"] <= 1.0

    breakdown = body["scoring_breakdown"]
    components = breakdown["components"]
    assert components["jurisdiction_risk"]["value"] == (100 - 15) / 100
    assert components["pep_component"]["value"] == 1.0  # direct PEP multiplier (2.0) / 2.0
    assert components["gift_hospitality_risk"]["value"] == 1.0
    assert components["industry_risk"]["value"] == 1.0


def test_compute_low_risk_high_cpi_no_pep_no_gifts_low_risk_industry(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-low")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Low Risk Vendor")

    response = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Cleanland",
            "jurisdiction_cpi_score": 90,
            "pep_exposure": "none",
            "gift_hospitality_log": [],
            "industry_category": "software_saas",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["risk_tier"] == "low"
    assert 0.0 <= body["risk_score"] <= 1.0


def test_compute_missing_cpi_uses_conservative_default(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-nocpi")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Unknown Jurisdiction Vendor")

    response = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Unrated Territory",
            "pep_exposure": "none",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["jurisdiction_cpi_score"] is None
    jurisdiction_component = body["scoring_breakdown"]["components"]["jurisdiction_risk"]
    assert jurisdiction_component["value"] == 0.7
    assert jurisdiction_component["source"] == "unknown_cpi_conservative_default"
    assert 0.0 <= body["risk_score"] <= 1.0


def test_compute_invalid_pep_exposure_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-badpep")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={"jurisdiction": "Somewhere", "pep_exposure": "totally_invalid"},
    )
    assert response.status_code == 422, response.text


def test_compute_negative_gift_value_returns_422(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-neggift")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    response = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Somewhere",
            "pep_exposure": "none",
            "gift_hospitality_log": [{"date": "2026-01-01", "description": "bad", "value_usd": -50.0}],
        },
    )
    assert response.status_code == 422, response.text


def test_vendor_not_in_org_returns_404(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-404")
    import uuid

    fake_vendor_id = uuid.uuid4()
    response = client.post(
        f"{BRIBERY_BASE}/{fake_vendor_id}/bribery-risk/compute",
        headers=org["org_headers"],
        json={"jurisdiction": "Somewhere", "pep_exposure": "none"},
    )
    assert response.status_code == 404, response.text

    response_get = client.get(f"{BRIBERY_BASE}/{fake_vendor_id}/bribery-risk", headers=org["org_headers"])
    assert response_get.status_code == 404, response_get.text


def test_history_newest_first_and_latest_404_when_empty(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-history")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"])

    latest_empty = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk", headers=org["org_headers"])
    assert latest_empty.status_code == 404, latest_empty.text
    assert "not found" in latest_empty.json()["detail"].lower() or "no anti-bribery" in latest_empty.json()["detail"].lower()

    history_empty = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/history", headers=org["org_headers"])
    assert history_empty.status_code == 200, history_empty.text
    assert history_empty.json() == []

    first = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={"jurisdiction": "First", "jurisdiction_cpi_score": 80, "pep_exposure": "none"},
    )
    assert first.status_code == 201, first.text

    second = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={"jurisdiction": "Second", "jurisdiction_cpi_score": 20, "pep_exposure": "direct"},
    )
    assert second.status_code == 201, second.text

    history = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/history", headers=org["org_headers"])
    assert history.status_code == 200, history.text
    rows = history.json()
    assert len(rows) == 2
    assert rows[0]["jurisdiction"] == "Second"
    assert rows[1]["jurisdiction"] == "First"

    latest = client.get(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk", headers=org["org_headers"])
    assert latest.status_code == 200, latest.text
    assert latest.json()["jurisdiction"] == "Second"

    for row in rows:
        assert 0.0 <= row["risk_score"] <= 1.0
