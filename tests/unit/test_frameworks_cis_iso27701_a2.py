from __future__ import annotations

from sqlalchemy import inspect, select

from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.framework import Framework
from app.models.obligation import Obligation
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


def test_cis_framework_seeded_with_expected_counts(db_session):
    _seed_frameworks(db_session)
    cis = _framework(db_session, "CIS Controls")

    rows = db_session.execute(select(Obligation).where(Obligation.framework_id == cis.id)).scalars().all()
    assert len(rows) == 153

    ig1 = [r for r in rows if r.ig_level == "IG1"]
    ig2 = [r for r in rows if r.ig_level == "IG2"]
    ig3 = [r for r in rows if r.ig_level == "IG3"]
    assert len(ig1) == 56
    assert len(ig2) == 74
    assert len(ig3) == 23


def test_cis_assess_applicability_scopes_by_ig(client, db_session):
    user = bootstrap_org_user(client, email_prefix="a2-cis-assess")
    _seed_frameworks(db_session)
    cis = _framework(db_session, "CIS Controls")

    ig1 = client.post(
        f"/api/v1/compliance/frameworks/{cis.id}/assess-applicability",
        headers=user["org_headers"],
        json={"answers": {"implementation_group": "IG1"}},
    )
    assert ig1.status_code == 200
    assert ig1.json()["applicable_obligation_count"] == 56

    ig2 = client.post(
        f"/api/v1/compliance/frameworks/{cis.id}/assess-applicability",
        headers=user["org_headers"],
        json={"answers": {"implementation_group": "IG2"}},
    )
    assert ig2.status_code == 200
    assert ig2.json()["applicable_obligation_count"] == 130

    ig3 = client.post(
        f"/api/v1/compliance/frameworks/{cis.id}/assess-applicability",
        headers=user["org_headers"],
        json={"answers": {"implementation_group": "IG3"}},
    )
    assert ig3.status_code == 200
    assert ig3.json()["applicable_obligation_count"] == 153

    q = client.get(
        f"/api/v1/compliance/frameworks/{cis.id}/applicability-questions",
        headers=user["org_headers"],
    )
    assert q.status_code == 200
    keys = {row["question_key"] for row in q.json()}
    assert "implementation_group" in keys


def test_iso_27701_seed_and_cross_mapping_endpoints(client, db_session):
    user = bootstrap_org_user(client, email_prefix="a2-iso")
    _seed_frameworks(db_session)
    iso = _framework(db_session, "ISO 27701")

    rows = db_session.execute(select(Obligation).where(Obligation.framework_id == iso.id)).scalars().all()
    ctrl = [r for r in rows if r.reference_code.startswith("27701-7.")]
    proc = [r for r in rows if r.reference_code.startswith("27701-8.")]
    assert len(ctrl) >= 15
    assert len(proc) >= 10

    tables = set(inspect(db_session.bind).get_table_names())
    assert "cross_framework_obligation_mappings" in tables

    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    assert len(mappings) >= 7

    framework_map_resp = client.get(
        f"/api/v1/compliance/frameworks/{iso.id}/cross-mappings",
        headers=user["org_headers"],
    )
    assert framework_map_resp.status_code == 200
    assert framework_map_resp.json()

    one_obligation = ctrl[0]
    obligation_map_resp = client.get(
        f"/api/v1/compliance/obligations/{one_obligation.id}/cross-mappings",
        headers=user["org_headers"],
    )
    assert obligation_map_resp.status_code == 200


def test_idempotent_second_seed_run_no_duplicates(db_session):
    _seed_frameworks(db_session)
    _seed_frameworks(db_session)

    cis = _framework(db_session, "CIS Controls")
    iso = _framework(db_session, "ISO 27701")

    cis_count = db_session.execute(select(Obligation).where(Obligation.framework_id == cis.id)).scalars().all()
    iso_count = db_session.execute(select(Obligation).where(Obligation.framework_id == iso.id)).scalars().all()
    assert len(cis_count) == 153
    assert len(iso_count) >= 25

    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    # Expect seeded unique mappings only once.
    assert len(mappings) >= 7
