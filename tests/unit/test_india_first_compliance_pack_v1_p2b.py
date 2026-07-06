from __future__ import annotations

from sqlalchemy import select

from app.models.framework import Framework
from app.models.obligation import Obligation
from app.services.seed_service import SeedService


def _seed_frameworks(db_session) -> None:
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_framework_versions(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()


def test_india_first_pack_frameworks_and_obligations_seeded(db_session):
    _seed_frameworks(db_session)

    expected_codes = {
        "RBI_IT_GOV",
        "RBI_CLOUD_OUTSOURCING",
        "SEBI_CSCRF",
        "SEBI_CLOUD",
        "IRDAI_CYBER_2023",
        "CERT_IN_2022",
        "INDIA_IT_ACT",
        "MCA_COMPLIANCE_CAL",
        "DPIIT_STARTUP",
    }
    rows = db_session.execute(select(Framework).where(Framework.code.in_(expected_codes))).scalars().all()
    assert {row.code for row in rows} == expected_codes

    certin = next(row for row in rows if row.code == "CERT_IN_2022")
    certin_obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == certin.id)).scalars().all()
    certin_refs = {row.reference_code for row in certin_obligations}
    assert {"CERTIN-01", "CERTIN-02"}.issubset(certin_refs)
    report_rule = next(row for row in certin_obligations if row.reference_code == "CERTIN-01")
    assert "six hours" in (report_rule.description or "").lower()

    mca = next(row for row in rows if row.code == "MCA_COMPLIANCE_CAL")
    mca_obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == mca.id)).scalars().all()
    assert len(mca_obligations) >= 1
    assert "compliance calendar" in (mca_obligations[0].description or "").lower()

    dpiit = next(row for row in rows if row.code == "DPIIT_STARTUP")
    dpiit_obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == dpiit.id)).scalars().all()
    assert len(dpiit_obligations) >= 2
    assert any("recognition" in (row.title or "").lower() for row in dpiit_obligations)


def test_india_first_pack_seed_is_idempotent(db_session):
    _seed_frameworks(db_session)

    before = db_session.execute(
        select(Obligation.reference_code).where(
            Obligation.reference_code.in_(
                [
                    "RBI-ITGRC-01",
                    "RBI-OUT-01",
                    "SEBI-CSCRF-01",
                    "IRDAI-CS-01",
                    "CERTIN-01",
                    "ITACT-01",
                    "MCA-CAL-01",
                    "DPIIT-01",
                ]
            )
        )
    ).all()
    before_count = len(before)

    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()

    after = db_session.execute(
        select(Obligation.reference_code).where(
            Obligation.reference_code.in_(
                [
                    "RBI-ITGRC-01",
                    "RBI-OUT-01",
                    "SEBI-CSCRF-01",
                    "IRDAI-CS-01",
                    "CERTIN-01",
                    "ITACT-01",
                    "MCA-CAL-01",
                    "DPIIT-01",
                ]
            )
        )
    ).all()
    assert len(after) == before_count
