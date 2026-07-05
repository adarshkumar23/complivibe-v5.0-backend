from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.permission import Permission
from app.models.vendor import Vendor
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


def test_t1_4_permissions_and_missing_profile_default(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t14-default")
    vendor = _create_vendor(client, org)

    keys = {row.key for row in db_session.query(Permission).all()}
    assert "vendor_criticality:read" in keys
    assert "vendor_criticality:manage" in keys

    settings = client.get(f"{VENDORS_BASE}/criticality/settings", headers=org["org_headers"])
    assert settings.status_code == 200, settings.text
    assert settings.json()["is_default"] is True
    assert settings.json()["revenue_dependency_weight"] == "0.2500"

    profile = client.get(f"{VENDORS_BASE}/{vendor['id']}/criticality", headers=org["org_headers"])
    assert profile.status_code == 200, profile.text
    body = profile.json()
    assert body["is_default"] is True
    assert body["revenue_dependency_pct"] == "0.00"
    assert body["data_volume_tier"] == "none"
    assert body["operational_criticality"] == "low"
    assert body["substitutability_score"] == 1
    assert body["criticality_score"] == 10
    assert body["criticality_tier"] == "low"


def test_t1_4_weighted_formula_updates_vendor_tier_and_audits(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t14-formula")
    vendor = _create_vendor(client, org, name="Weighted Vendor")

    settings = client.put(
        f"{VENDORS_BASE}/criticality/settings",
        headers=org["org_headers"],
        json={
            "revenue_dependency_weight": "0.4000",
            "data_volume_weight": "0.3000",
            "operational_criticality_weight": "0.2000",
            "substitutability_weight": "0.1000",
        },
    )
    assert settings.status_code == 200, settings.text

    profile = client.put(
        f"{VENDORS_BASE}/{vendor['id']}/criticality",
        headers=org["org_headers"],
        json={
            "revenue_dependency_pct": "60.00",
            "data_volume_tier": "high",
            "operational_criticality": "critical",
            "substitutability_score": 5,
            "notes": "Core revenue processing vendor",
        },
    )
    assert profile.status_code == 200, profile.text
    body = profile.json()

    # Hand check:
    # revenue 60% -> 60/20 = 3.0; data high = 4; operational critical = 5; substitutability = 5.
    # Weighted 0-5 score = (3*.4 + 4*.3 + 5*.2 + 5*.1) / 1.0 = 3.9.
    # Projected 0-100 score = round(3.9/5*100) = 78, which maps to critical.
    assert body["criticality_score"] == 78
    assert body["criticality_tier"] == "critical"
    assert body["score_explanation_json"]["formula"] == "round_0_100(sum(normalized_0_to_5 * weight) / sum(weights) / 5 * 100)"
    assert body["score_explanation_json"]["normalized_values_0_to_5"]["revenue_dependency"] == "3.00"
    assert body["score_explanation_json"]["weights"]["revenue_dependency_weight"] == "0.4000"
    assert body["score_explanation_json"]["sources"]

    refreshed_vendor = db_session.get(Vendor, uuid.UUID(vendor["id"]))
    assert refreshed_vendor.risk_tier == "critical"

    audits = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action.in_(["vendor_criticality_profile.updated", "vendor.risk_tier.updated"]),
        )
    ).scalars().all()
    assert {row.action for row in audits} == {"vendor_criticality_profile.updated", "vendor.risk_tier.updated"}
    tier_audit = next(row for row in audits if row.action == "vendor.risk_tier.updated")
    assert tier_audit.after_json["criticality_score"] == 78
