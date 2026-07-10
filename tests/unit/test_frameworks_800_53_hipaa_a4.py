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


def test_phase1_framework_quick_win_seed_counts_and_idempotency(client, db_session):
    org = bootstrap_org_user(client, email_prefix="phase1-frameworks")
    _seed_frameworks(db_session)
    _seed_frameworks(db_session)

    nist = _framework(db_session, "NIST SP 800-53")
    moderate_resp = client.post(
        f"/api/v1/compliance/frameworks/{nist.id}/assess-applicability",
        headers=org["org_headers"],
        json={"answers": {"federal_system": True, "impact_level": "MODERATE"}},
    )
    assert moderate_resp.status_code == 200
    assert moderate_resp.json()["applicable_obligation_count"] == 325

    high_resp = client.post(
        f"/api/v1/compliance/frameworks/{nist.id}/assess-applicability",
        headers=org["org_headers"],
        json={"answers": {"federal_system": True, "impact_level": "HIGH"}},
    )
    assert high_resp.status_code == 200
    assert high_resp.json()["applicable_obligation_count"] == 421

    csa = _framework(db_session, "CSA STAR CCM")
    csa_rows = db_session.execute(
        select(Obligation).where(Obligation.framework_id == csa.id, Obligation.status == "active")
    ).scalars().all()
    assert len(csa_rows) == 197
    ais_01 = next(row for row in csa_rows if row.reference_code == "AIS-01")
    assert "application security" in (ais_01.description or "").lower()

    cra = _framework(db_session, "EU CRA Annex IV")
    cra_rows = db_session.execute(
        select(Obligation).where(Obligation.framework_id == cra.id, Obligation.status == "active")
    ).scalars().all()
    assert len(cra_rows) == 3
    assert {row.reference_code for row in cra_rows} == {"CRA-IV-1", "CRA-IV-2", "CRA-IV-3"}

    dpdp = _framework(db_session, "India DPDP")
    dpdp_rows = db_session.execute(
        select(Obligation).where(Obligation.framework_id == dpdp.id, Obligation.status == "active")
    ).scalars().all()
    assert len(dpdp_rows) == 21  # DPDP-SDF-1/2/3 split from DPDP-S10-SDF, plus DPDP-RULE-ACCOUNTABILITY (ported from the retired india_dpdp_starter.json pack)
    assert any(row.reference_code == "DPDP-RULE-BREACH" and "without delay" in (row.description or "") for row in dpdp_rows)
    assert all(row.reference_code != "DPDP-S16-2" for row in dpdp_rows)

    obligations = db_session.execute(select(Obligation)).scalars().all()
    by_id = {row.id: row for row in obligations}
    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    csa_iso_mappings = [
        row
        for row in mappings
        if by_id.get(row.source_obligation_id) is not None
        and by_id.get(row.target_obligation_id) is not None
        and by_id[row.source_obligation_id].reference_code.startswith("AIS-")
        and by_id[row.target_obligation_id].reference_code.startswith("A.")
    ]
    assert csa_iso_mappings


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
