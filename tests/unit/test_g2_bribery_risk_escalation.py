from __future__ import annotations

import uuid

from app.models.risk import Risk
from app.models.vendor import Vendor
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


def test_high_bribery_risk_escalates_under_tiered_vendor_and_creates_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-escalate")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Under-Tiered Vendor")
    assert vendor["risk_tier"] == "not_assessed"

    response = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Corruptistan",
            "jurisdiction_cpi_score": 10,
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
    assert "inconsistent_with_vendor_overall_risk_tier" in " ".join(body["context_flags"])

    # The flag must actually have been acted on: vendor risk_tier escalated...
    assert body["risk_tier_escalated"] is True
    assert body["risk_created"] is True
    assert body["risk_id"]

    db_session.expire_all()
    vendor_row = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert vendor_row.risk_tier == "high"
    assert vendor_row.risk_tier_source == "computed"

    # ...and a real Risk record created and linked.
    risk_row = db_session.get(Risk, uuid.UUID(body["risk_id"]))
    assert risk_row is not None
    assert risk_row.organization_id == vendor_row.organization_id
    assert "Under-Tiered Vendor" in risk_row.title


def test_high_bribery_risk_does_not_reescalate_or_duplicate_risk_on_recompute(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-idempotent")
    vendor = _create_vendor(client, org["org_headers"], org["user_id"], name="Repeat Vendor")

    payload = {
        "jurisdiction": "Corruptistan",
        "jurisdiction_cpi_score": 10,
        "pep_exposure": "direct",
        "gift_hospitality_log": [{"date": "2026-01-01", "description": "gift", "value_usd": 5000.0}],
        "industry_category": "defense",
    }

    first = client.post(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute", headers=org["org_headers"], json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["risk_tier_escalated"] is True
    first_risk_id = first.json()["risk_id"]

    second = client.post(f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute", headers=org["org_headers"], json=payload)
    assert second.status_code == 201, second.text
    # Vendor is already at 'high' now, so no longer "under-tiered" -- no re-escalation.
    assert second.json()["risk_tier_escalated"] is False
    assert second.json()["risk_created"] is False
    assert second.json()["risk_id"] is None
    assert first_risk_id is not None


def test_high_bribery_risk_does_not_escalate_when_vendor_already_at_or_above_high(client, db_session):
    org = bootstrap_org_user(client, email_prefix="abc-already")
    response = client.post(
        VENDORS_BASE,
        headers=org["org_headers"],
        json={
            "name": "Already High Vendor",
            "vendor_type": "software",
            "owner_user_id": org["user_id"],
            "risk_tier": "critical",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    vendor = response.json()

    compute = client.post(
        f"{BRIBERY_BASE}/{vendor['id']}/bribery-risk/compute",
        headers=org["org_headers"],
        json={
            "jurisdiction": "Corruptistan",
            "jurisdiction_cpi_score": 10,
            "pep_exposure": "direct",
            "gift_hospitality_log": [{"date": "2026-01-01", "description": "gift", "value_usd": 5000.0}],
            "industry_category": "defense",
        },
    )
    assert compute.status_code == 201, compute.text
    body = compute.json()
    assert body["risk_tier"] == "high"
    assert body["risk_tier_escalated"] is False
    assert body["risk_created"] is False

    db_session.expire_all()
    vendor_row = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert vendor_row.risk_tier == "critical"
