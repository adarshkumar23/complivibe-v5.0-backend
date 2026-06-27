from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.compliance.services.gdpr_ropa_builder import GDPRArticle30Builder
from app.compliance.services.subprocessor_service import SubprocessorService
from app.data_observability.services.residency_service import EEA_COUNTRIES
from app.models.audit_log import AuditLog
from app.models.data_incident import DataIncident
from app.models.framework import Framework
from app.models.obligation import Obligation
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
OBLIGATION_COVERAGE_BASE = "/api/v1/data-observability/obligation-coverage"
DASHBOARD_BASE = "/api/v1/data-observability/dashboard"
RESIDENCY_BASE = "/api/v1/data-observability/residency"


def _create_asset(client, headers: dict[str, str], owner_id: str, name: str, *, locations: list[str]) -> str:
    response = client.post(
        ASSETS_BASE,
        headers=headers,
        json={
            "name": name,
            "asset_type": "table",
            "owner_id": owner_id,
            "description": "asset for obligation/residency tests",
            "schema_column_names": ["email", "customer_id"],
            "geographic_locations": locations,
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _get_or_create_framework(db_session, *, code: str, name: str, jurisdiction: str = "International") -> Framework:
    existing = db_session.query(Framework).filter(Framework.code == code).first()
    if existing is not None:
        return existing
    row = Framework(
        code=code,
        name=name,
        description=f"{name} framework",
        category="Privacy",
        jurisdiction=jurisdiction,
        authority=name,
        version="1.0",
        status="active",
        coverage_level="starter",
        source_url=None,
        effective_date=None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def _create_obligation(db_session, framework_id: uuid.UUID, ref: str, title: str, jurisdiction: str = "International") -> Obligation:
    row = Obligation(
        framework_id=framework_id,
        framework_section_id=None,
        reference_code=ref,
        title=title,
        description=title,
        plain_language_summary=None,
        obligation_type="requirement",
        jurisdiction=jurisdiction,
        source_url=None,
        version="1.0",
        status="active",
        effective_date=None,
        parent_obligation_id=None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_c81_data_to_obligation_linking(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c81-org")

    asset_1 = _create_asset(client, org["org_headers"], org["user_id"], "personal_asset", locations=["DE"])
    asset_2 = _create_asset(client, org["org_headers"], org["user_id"], "unlinked_asset", locations=["DE"])

    # Ensure deterministic obligation pool for suggestions.
    gdpr_fw = _get_or_create_framework(db_session, code="GDPR", name="GDPR", jurisdiction="European Union")
    dpdp_fw = _get_or_create_framework(db_session, code="INDIA_DPDP", name="India DPDP", jurisdiction="India")
    hipaa_fw = _get_or_create_framework(db_session, code="HIPAA", name="HIPAA", jurisdiction="United States")

    gdpr_ob = _create_obligation(db_session, gdpr_fw.id, "GDPR-ART30", "Records of processing activities", "European Union")
    dpdp_ob = _create_obligation(db_session, dpdp_fw.id, "DPDP-SEC8", "Data fiduciary obligations", "India")
    hipaa_ob = _create_obligation(db_session, hipaa_fw.id, "HIPAA-164", "Safeguards", "United States")

    link_resp = client.post(
        f"{ASSETS_BASE}/{asset_1}/obligation-links",
        headers=org["org_headers"],
        json={
            "obligation_id": str(gdpr_ob.id),
            "link_type": "governed_by",
            "justification": "Contains EU personal data",
        },
    )
    assert link_resp.status_code == 201
    assert link_resp.json()["framework_name"] == "GDPR"

    duplicate = client.post(
        f"{ASSETS_BASE}/{asset_1}/obligation-links",
        headers=org["org_headers"],
        json={
            "obligation_id": str(gdpr_ob.id),
            "link_type": "governed_by",
        },
    )
    assert duplicate.status_code == 409

    linked = client.get(f"{ASSETS_BASE}/{asset_1}/obligation-links", headers=org["org_headers"])
    assert linked.status_code == 200
    assert len(linked.json()) == 1
    assert linked.json()[0]["framework_name"] == "GDPR"
    assert linked.json()[0]["obligation_title"] == "Records of processing activities"

    obligation_assets = client.get(
        f"/api/v1/compliance/obligations/{gdpr_ob.id}/data-assets",
        headers=org["org_headers"],
    )
    assert obligation_assets.status_code == 200
    assert any(row["asset_id"] == asset_1 for row in obligation_assets.json())

    coverage = client.get(OBLIGATION_COVERAGE_BASE, headers=org["org_headers"])
    assert coverage.status_code == 200
    coverage_body = coverage.json()
    assert coverage_body["total_assets"] == 2
    assert coverage_body["linked_assets"] == 1
    assert float(coverage_body["coverage_pct"]) == 50.0

    suggest_personal = client.get(f"{ASSETS_BASE}/{asset_1}/suggest-obligations", headers=org["org_headers"])
    assert suggest_personal.status_code == 200
    frameworks = {item["framework_code"] for item in suggest_personal.json()}
    assert "GDPR" in frameworks
    assert "INDIA_DPDP" in frameworks

    # Health asset should suggest HIPAA.
    health_asset = _create_asset(client, org["org_headers"], org["user_id"], "health_asset", locations=["DE"])
    patch_health = client.patch(
        f"{ASSETS_BASE}/{health_asset}",
        headers=org["org_headers"],
        json={"classification_type": "health_data", "sensitivity_tier": "restricted"},
    )
    assert patch_health.status_code == 200

    suggest_health = client.get(f"{ASSETS_BASE}/{health_asset}/suggest-obligations", headers=org["org_headers"])
    assert suggest_health.status_code == 200
    assert any(item["framework_code"] == "HIPAA" for item in suggest_health.json())

    # RoPA builder now returns full Article 30 shape.
    ropa = GDPRArticle30Builder.build(uuid.UUID(org["organization_id"]), db_session)
    assert ropa["status"] == "empty"
    assert isinstance(ropa["activities"], list)

    # Dashboard now uses real obligation coverage (no placeholder status).
    dashboard = client.get(DASHBOARD_BASE, headers=org["org_headers"])
    assert dashboard.status_code == 200
    assert "status" not in dashboard.json()["data_obligation_coverage"]
    assert dashboard.json()["data_obligation_coverage"]["linked_assets"] >= 1

    # Unlink and verify removal + audit event.
    unlink = client.delete(f"{ASSETS_BASE}/{asset_1}/obligation-links/{gdpr_ob.id}", headers=org["org_headers"])
    assert unlink.status_code == 204

    linked_after = client.get(f"{ASSETS_BASE}/{asset_1}/obligation-links", headers=org["org_headers"])
    assert linked_after.status_code == 200
    assert linked_after.json() == []

    audit = (
        db_session.query(AuditLog)
        .filter(
            AuditLog.organization_id == uuid.UUID(org["organization_id"]),
            AuditLog.action == "data_obligation.unlinked",
        )
        .first()
    )
    assert audit is not None

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="c81-org-b")
    isolated = client.get(OBLIGATION_COVERAGE_BASE, headers=org_b["org_headers"])
    assert isolated.status_code == 200
    assert isolated.json()["linked_assets"] == 0

    _ = dpdp_ob, hipaa_ob


def test_c82_data_residency_monitoring(client, db_session):
    org = bootstrap_org_user(client, email_prefix="c82-org")

    us_asset = _create_asset(client, org["org_headers"], org["user_id"], "asset_us", locations=["US"])
    de_asset = _create_asset(client, org["org_headers"], org["user_id"], "asset_de", locations=["DE"])

    # Ensure reused constant.
    assert EEA_COUNTRIES == set(SubprocessorService.EEA_COUNTRIES)

    policy = client.post(
        f"{RESIDENCY_BASE}/policies",
        headers=org["org_headers"],
        json={
            "name": "EEA only",
            "require_eea_only": True,
            "applies_to_classification_types": [],
            "applies_to_sensitivity_tiers": [],
        },
    )
    assert policy.status_code == 201

    us_check = client.post(f"{RESIDENCY_BASE}/check-asset/{us_asset}", headers=org["org_headers"])
    assert us_check.status_code == 200
    assert us_check.json()["compliant"] is False

    de_check = client.post(f"{RESIDENCY_BASE}/check-asset/{de_asset}", headers=org["org_headers"])
    assert de_check.status_code == 200
    assert de_check.json()["compliant"] is True

    # Add prohibited and required checks.
    policy_2 = client.post(
        f"{RESIDENCY_BASE}/policies",
        headers=org["org_headers"],
        json={
            "name": "No US + must include DE",
            "prohibited_countries": ["US"],
            "required_countries": ["DE"],
        },
    )
    assert policy_2.status_code == 201

    check_prohibited_missing = client.post(f"{RESIDENCY_BASE}/check-asset/{us_asset}", headers=org["org_headers"])
    assert check_prohibited_missing.status_code == 200
    violations = [v for p in check_prohibited_missing.json()["policy_results"] for v in p["violations"]]
    types = {v["type"] for v in violations}
    assert "data_in_prohibited_country" in types
    assert "data_outside_required_country" in types

    sweep_1 = client.post(f"{RESIDENCY_BASE}/trigger-sweep", headers=org["org_headers"])
    assert sweep_1.status_code == 200
    assert sweep_1.json()["violations_found"] >= 1
    assert sweep_1.json()["incidents_created"] >= 1

    # Dedup open violations on subsequent sweep.
    sweep_2 = client.post(f"{RESIDENCY_BASE}/trigger-sweep", headers=org["org_headers"])
    assert sweep_2.status_code == 200
    assert sweep_2.json()["violations_found"] == 0

    violations_list = client.get(f"{RESIDENCY_BASE}/violations?status=open", headers=org["org_headers"])
    assert violations_list.status_code == 200
    assert len(violations_list.json()) >= 1
    first_violation_id = violations_list.json()[0]["id"]

    ack = client.post(f"{RESIDENCY_BASE}/violations/{first_violation_id}/acknowledge", headers=org["org_headers"])
    assert ack.status_code == 200
    assert ack.json()["status"] == "acknowledged"

    summary = client.get(f"{RESIDENCY_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    assert 0.0 <= float(summary.json()["eea_compliant_pct"]) <= 100.0

    # Incident exists for residency violation.
    incidents = (
        db_session.query(DataIncident)
        .filter(
            DataIncident.organization_id == uuid.UUID(org["organization_id"]),
            DataIncident.detector_type == "residency_violation",
        )
        .all()
    )
    assert len(incidents) >= 1

    # Asset endpoint for residency status.
    asset_status = client.get(f"{ASSETS_BASE}/{us_asset}/residency-status", headers=org["org_headers"])
    assert asset_status.status_code == 200
    assert asset_status.json()["asset_id"] == us_asset

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="c82-org-b")
    isolated = client.get(f"{RESIDENCY_BASE}/violations", headers=org_b["org_headers"])
    assert isolated.status_code == 200
    assert isolated.json() == []
