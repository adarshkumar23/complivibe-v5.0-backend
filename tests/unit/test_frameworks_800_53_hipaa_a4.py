from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.compliance.services.incident_sla_service import get_framework_sla_hours
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.dpa_agreement import DPAAgreement
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.obligation import Obligation
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user

ASSETS_BASE = "/api/v1/data-observability/assets"
DPA_BASE = "/api/v1/privacy/dpas"


def _seed_frameworks(db_session) -> None:
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_framework_versions(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()


def _framework(db_session, name: str) -> Framework:
    row = db_session.execute(select(Framework).where(Framework.name == name)).scalar_one_or_none()
    assert row is not None
    return row


def test_nist_800_53_seed_and_assess_low(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a4-nist")
    _seed_frameworks(db_session)

    framework = _framework(db_session, "NIST SP 800-53")

    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
    active_low = [row for row in obligations if row.status == "active" and row.baseline == "LOW"]
    sections = db_session.execute(select(FrameworkSection).where(FrameworkSection.framework_id == framework.id)).scalars().all()

    assert len(active_low) == 125
    assert len(sections) == 20

    columns = {col["name"] for col in inspect(db_session.bind).get_columns("obligations")}
    assert "control_family" in columns
    assert "baseline" in columns

    ac2 = next(row for row in active_low if row.reference_code == "AC-2")
    assert ac2.baseline == "LOW"
    assert ac2.control_family == "AC"

    assess_resp = client.post(
        f"/api/v1/compliance/frameworks/{framework.id}/assess-applicability",
        headers=org["org_headers"],
        json={"answers": {"federal_system": True, "impact_level": "LOW"}},
    )
    assert assess_resp.status_code == 200
    assert assess_resp.json()["applicable_obligation_count"] == 125


def test_hipaa_schema_seed_and_sla_wiring(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a4-hipaa")
    _seed_frameworks(db_session)

    hipaa = _framework(db_session, "HIPAA")
    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == hipaa.id)).scalars().all()
    sections = db_session.execute(select(FrameworkSection).where(FrameworkSection.framework_id == hipaa.id)).scalars().all()

    assert len(obligations) >= 22
    assert len(sections) == 3

    dpa_columns = {col["name"] for col in inspect(db_session.bind).get_columns("dpa_agreements")}
    assert "is_baa" in dpa_columns
    assert "baa_includes_phi" in dpa_columns

    asset_columns = {col["name"] for col in inspect(db_session.bind).get_columns("data_assets")}
    assert "is_phi" in asset_columns
    assert "hipaa_safeguard_required" in asset_columns

    dpa_resp = client.post(
        DPA_BASE,
        headers=org["org_headers"],
        json={
            "counterparty_name": "HIPAA BA",
            "counterparty_type": "processor",
            "status": "active",
            "owner_id": org["user_id"],
            "governing_regulation": ["hipaa"],
            "is_baa": True,
            "baa_includes_phi": True,
            "hipaa_covered_entity_type": "business_associate",
        },
    )
    assert dpa_resp.status_code == 201
    dpa_body = dpa_resp.json()
    assert dpa_body["is_baa"] is True
    assert dpa_body["hipaa_covered_entity_type"] == "business_associate"

    dpa_row = db_session.get(DPAAgreement, UUID(dpa_body["id"]))
    assert dpa_row is not None
    assert dpa_row.hipaa_covered_entity_type == "business_associate"

    asset_resp = client.post(
        ASSETS_BASE,
        headers=org["org_headers"],
        json={
            "name": "hipaa_asset",
            "asset_type": "database",
            "owner_id": org["user_id"],
            "description": "Contains PHI",
            "is_phi": True,
            "hipaa_safeguard_required": "all",
        },
    )
    assert asset_resp.status_code == 201
    asset_body = asset_resp.json()
    assert asset_body["is_phi"] is True
    assert asset_body["hipaa_safeguard_required"] == "all"

    assert get_framework_sla_hours("hipaa") == 1440
    assert get_framework_sla_hours("gdpr") == 72

    hipaa_ids = {row.id for row in obligations}
    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    hipaa_related = [row for row in mappings if row.source_obligation_id in hipaa_ids]
    assert len(hipaa_related) >= 5
