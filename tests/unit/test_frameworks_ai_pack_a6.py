from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


def _seed_frameworks(db_session) -> None:
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_framework_versions(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()


def _framework(db_session, name: str) -> Framework:
    row = db_session.execute(select(Framework).where(Framework.name == name)).scalar_one_or_none()
    assert row is not None
    return row


def _obligation_count(db_session, framework_name: str) -> int:
    framework = _framework(db_session, framework_name)
    return len(db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all())


def test_iso_31000_schema_and_vocab_fields(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a6-iso31000")
    _seed_frameworks(db_session)

    framework = _framework(db_session, "ISO 31000")
    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
    assert len(obligations) >= 20

    columns = {col["name"] for col in inspect(db_session.bind).get_columns("risks")}
    assert "treatment_option" in columns
    assert "residual_risk_acceptable" in columns

    create_reduce = client.post(
        "/api/v1/risks",
        headers=org["org_headers"],
        json={
            "title": "ISO31000 Risk Reduce",
            "category": "security",
            "likelihood": 3,
            "impact": 3,
            "treatment_option": "reduce",
        },
    )
    assert create_reduce.status_code == 201
    reduce_body = create_reduce.json()
    assert reduce_body["treatment_option"] == "reduce"

    create_share = client.post(
        "/api/v1/risks",
        headers=org["org_headers"],
        json={
            "title": "ISO31000 Risk Share",
            "category": "security",
            "likelihood": 3,
            "impact": 4,
            "treatment_option": "share",
        },
    )
    assert create_share.status_code == 201
    share_body = create_share.json()
    assert share_body["treatment_option"] == "share"

    reduce_row = db_session.get(Risk, UUID(reduce_body["id"]))
    share_row = db_session.get(Risk, UUID(share_body["id"]))
    assert reduce_row is not None and reduce_row.treatment_option == "reduce"
    assert share_row is not None and share_row.treatment_option == "share"


def test_ai_governance_pack_frameworks_and_mappings(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a6-aigov")
    _seed_frameworks(db_session)

    assert _obligation_count(db_session, "OECD AI Principles") >= 10
    assert _obligation_count(db_session, "IEEE 7000 Series") >= 10
    assert _obligation_count(db_session, "UNESCO AI Ethics") >= 13
    assert _obligation_count(db_session, "Singapore Model AI Governance") >= 12
    assert _obligation_count(db_session, "G7 Hiroshima AI Process") >= 11
    assert _obligation_count(db_session, "MITRE ATLAS") >= 14

    atlas = _framework(db_session, "MITRE ATLAS")
    q_resp = client.get(f"/api/v1/compliance/frameworks/{atlas.id}/applicability-questions", headers=org["org_headers"])
    assert q_resp.status_code == 200
    keys = {row["question_key"] for row in q_resp.json()}
    assert "deploys_ml_systems" in keys

    obligations = db_session.execute(select(Obligation)).scalars().all()
    by_id = {row.id: row for row in obligations}
    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()

    g7_oecd = [
        row
        for row in mappings
        if by_id.get(row.source_obligation_id) is not None
        and by_id.get(row.target_obligation_id) is not None
        and by_id[row.source_obligation_id].reference_code.startswith("G7-HAP-")
        and by_id[row.target_obligation_id].reference_code.startswith("OECD-")
    ]
    assert len(g7_oecd) >= 3

    atlas_nist = [
        row
        for row in mappings
        if by_id.get(row.source_obligation_id) is not None
        and by_id.get(row.target_obligation_id) is not None
        and by_id[row.source_obligation_id].reference_code.startswith("ATLAS-")
        and (
            by_id[row.target_obligation_id].reference_code.startswith("GOVERN-")
            or by_id[row.target_obligation_id].reference_code.startswith("MAP-")
            or by_id[row.target_obligation_id].reference_code.startswith("MEASURE-")
            or by_id[row.target_obligation_id].reference_code.startswith("MANAGE-")
        )
    ]
    assert len(atlas_nist) >= 2


def test_phase1_checkpoint_and_endpoints(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a6-seal")
    _seed_frameworks(db_session)

    frameworks_resp = client.get("/api/v1/frameworks", headers=org["headers"])
    assert frameworks_resp.status_code == 200
    frameworks = frameworks_resp.json()
    assert len(frameworks) >= 17

    assert _obligation_count(db_session, "PCI DSS") == 78
    assert _obligation_count(db_session, "NIST CSF") == 108
    assert _obligation_count(db_session, "CIS Controls") == 153

    nist_800_53 = _framework(db_session, "NIST SP 800-53")
    nist_obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == nist_800_53.id)).scalars().all()
    assert len([row for row in nist_obligations if row.status == "active" and row.baseline == "LOW"]) == 125

    bind = db_session.bind
    assert bind is not None
    inspector = inspect(bind)

    obligations_cols = {col["name"] for col in inspector.get_columns("obligations")}
    assert "ig_level" in obligations_cols
    assert "baseline" in obligations_cols
    assert "control_family" in obligations_cols

    dpa_cols = {col["name"] for col in inspector.get_columns("dpa_agreements")}
    assert "is_baa" in dpa_cols
    assert "baa_includes_phi" in dpa_cols

    data_asset_cols = {col["name"] for col in inspector.get_columns("data_assets")}
    assert "is_phi" in data_asset_cols

    risks_cols = {col["name"] for col in inspector.get_columns("risks")}
    assert "treatment_option" in risks_cols
    assert "risk_context_internal" in risks_cols
    assert "residual_risk_acceptable" in risks_cols

    org_cols = {col["name"] for col in inspector.get_columns("organizations")}
    assert "is_significant_data_fiduciary" in org_cols

    breach_cols = {col["name"] for col in inspector.get_columns("breach_notifications")}
    assert "regulatory_framework" in breach_cols

    org_me = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert org_me.status_code == 200
    org_slug = org_me.json()[0]["slug"]

    ccpa_opt_out = client.post(
        "/api/v1/privacy/ccpa/opt-out",
        json={"subject_email": "seal@example.com", "subject_name": "Seal User", "org_slug": org_slug},
    )
    assert ccpa_opt_out.status_code in (200, 201)

    dora_ict = client.get("/api/v1/compliance/dora/ict-register", headers=org["org_headers"])
    assert dora_ict.status_code == 200

    # Seed idempotency for frameworks.
    before_framework_ids = {row.id for row in db_session.execute(select(Framework)).scalars().all()}
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_framework_versions(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()
    after_framework_ids = {row.id for row in db_session.execute(select(Framework)).scalars().all()}
    assert before_framework_ids == after_framework_ids
