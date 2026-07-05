from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.permission import Permission
from app.models.risk import Risk
from app.models.vendor_concentration_risk import VendorConcentrationRiskDetection
from tests.helpers.auth_org import bootstrap_org_user

VENDORS_BASE = "/api/v1/compliance/vendors"
SUPPLY_CHAIN_BASE = "/api/v1/vendors"
CONCENTRATION_BASE = "/api/v1/vendor-concentration-risk"


def _create_vendor(client, headers: dict[str, str], owner_user_id: str, *, name: str, risk_tier: str = "critical") -> dict:
    response = client.post(
        VENDORS_BASE,
        headers=headers,
        json={
            "name": name,
            "vendor_type": "software",
            "owner_user_id": owner_user_id,
            "risk_tier": risk_tier,
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _link_dependency(client, headers: dict[str, str], *, parent_vendor_id: str, sub_vendor_id: str) -> dict:
    response = client.post(
        f"{SUPPLY_CHAIN_BASE}/{parent_vendor_id}/supply-chain-links",
        headers=headers,
        json={"sub_vendor_id": sub_vendor_id, "relationship_type": "critical_dependency"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_t1_6_permissions_seeded(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t16-perms")

    keys = {p.key for p in db_session.query(Permission).all()}
    assert "vendor_concentration_risk:read" in keys
    assert "vendor_concentration_risk:manage" in keys

    response = client.get("/api/v1/auth/permissions", headers=org["org_headers"])
    assert response.status_code == 200
    codes = set(response.json()["permission_codes"])
    assert "vendor_concentration_risk:read" in codes
    assert "vendor_concentration_risk:manage" in codes


def test_t1_6_recompute_creates_single_risk_register_entry_for_breach(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t16-breach")

    shared = _create_vendor(client, org["org_headers"], org["user_id"], name="Shared Critical Platform")
    app_a = _create_vendor(client, org["org_headers"], org["user_id"], name="Critical App A")
    app_b = _create_vendor(client, org["org_headers"], org["user_id"], name="Critical App B")
    app_c = _create_vendor(client, org["org_headers"], org["user_id"], name="Critical App C")
    _link_dependency(client, org["org_headers"], parent_vendor_id=app_a["id"], sub_vendor_id=shared["id"])
    _link_dependency(client, org["org_headers"], parent_vendor_id=app_b["id"], sub_vendor_id=shared["id"])
    _link_dependency(client, org["org_headers"], parent_vendor_id=app_c["id"], sub_vendor_id=shared["id"])

    first = client.post(f"{CONCENTRATION_BASE}/recompute", headers=org["org_headers"], json={})
    assert first.status_code == 200, first.text
    body = first.json()
    detection = body["detection"]
    assert body["risk_created"] is True
    assert body["state_changed"] is True
    assert detection["status"] == "breach"
    assert detection["hhi_score"] >= 1800
    assert detection["threshold_hhi_score"] == 1800
    assert detection["top_vendor_id"] == shared["id"]
    assert detection["risk_id"] is not None
    assert detection["convention_source_url"].startswith("https://www.justice.gov/")
    assert detection["criticality_source_url"].startswith("https://www.federalregister.gov/")

    risk_id = uuid.UUID(detection["risk_id"])
    risk = db_session.get(Risk, risk_id)
    assert risk is not None
    assert risk.category == "vendor"
    assert risk.metadata_json["source"] == "vendor_concentration_risk"
    assert risk.metadata_json["detection_id"] == detection["id"]

    second = client.post(f"{CONCENTRATION_BASE}/recompute", headers=org["org_headers"], json={})
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert second_body["risk_created"] is False
    assert second_body["state_changed"] is False
    assert second_body["detection"]["risk_id"] == str(risk_id)

    risks = db_session.execute(
        select(Risk).where(
            Risk.organization_id == uuid.UUID(org["organization_id"]),
            Risk.category == "vendor",
        )
    ).scalars().all()
    generated = [row for row in risks if (row.metadata_json or {}).get("source") == "vendor_concentration_risk"]
    assert len(generated) == 1

    risk_audits = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "risk.created",
            AuditLog.entity_id == risk_id,
        )
    ).scalars().all()
    assert len(risk_audits) == 1

    detection_audits = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "vendor_concentration_risk.recomputed",
        )
    ).scalars().all()
    assert len(detection_audits) == 1


def test_t1_6_no_exposures_recompute_does_not_create_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="t16-empty")

    response = client.post(f"{CONCENTRATION_BASE}/recompute", headers=org["org_headers"], json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["risk_created"] is False
    assert body["detection"]["status"] == "below_threshold"
    assert body["detection"]["risk_id"] is None
    assert body["detection"]["exposure_count"] == 0

    rows = db_session.execute(
        select(VendorConcentrationRiskDetection).where(
            VendorConcentrationRiskDetection.organization_id == uuid.UUID(org["organization_id"])
        )
    ).scalars().all()
    assert len(rows) == 1
