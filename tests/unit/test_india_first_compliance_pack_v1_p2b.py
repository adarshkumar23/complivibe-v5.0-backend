from __future__ import annotations

from sqlalchemy import select

from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.obligation import Obligation
from app.models.obligation_applicability_question import ObligationApplicabilityQuestion
from app.models.obligation_applicability_rule import ObligationApplicabilityRule
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
    mca_annual_section = db_session.execute(
        select(FrameworkSection).where(
            FrameworkSection.framework_id == mca.id,
            FrameworkSection.section_code == "MCA-ANNUAL",
        )
    ).scalar_one()
    assert mca_annual_section.metadata_json.get("review_cycle_days") == 365
    assert "calendar_deadline_management_required" in mca_annual_section.metadata_json.get("context_flags", [])

    dpiit = next(row for row in rows if row.code == "DPIIT_STARTUP")
    dpiit_obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == dpiit.id)).scalars().all()
    assert len(dpiit_obligations) >= 2
    assert any("recognition" in (row.title or "").lower() for row in dpiit_obligations)

    cert_report_section = db_session.execute(
        select(FrameworkSection).where(
            FrameworkSection.framework_id == certin.id,
            FrameworkSection.section_code == "CERT-REPORT",
        )
    ).scalar_one()
    assert cert_report_section.metadata_json.get("freshness_sla_hours") == 6
    assert "certin_six_hour_reporting_window" in cert_report_section.metadata_json.get("context_flags", [])


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


def test_india_first_pack_applicability_rules_seeded_for_all_active_obligations(db_session):
    _seed_frameworks(db_session)

    frameworks = db_session.execute(
        select(Framework).where(
            Framework.code.in_(
                [
                    "RBI_IT_GOV",
                    "SEBI_CSCRF",
                    "IRDAI_CYBER_2023",
                    "CERT_IN_2022",
                    "INDIA_IT_ACT",
                    "MCA_COMPLIANCE_CAL",
                    "DPIIT_STARTUP",
                ]
            )
        )
    ).scalars().all()
    assert frameworks

    for framework in frameworks:
        obligations = db_session.execute(
            select(Obligation).where(Obligation.framework_id == framework.id, Obligation.status == "active")
        ).scalars().all()
        assert obligations

        questions = db_session.execute(
            select(ObligationApplicabilityQuestion).where(
                ObligationApplicabilityQuestion.framework_id == framework.id,
                ObligationApplicabilityQuestion.organization_id.is_(None),
                ObligationApplicabilityQuestion.obligation_id.is_(None),
                ObligationApplicabilityQuestion.status == "active",
            )
        ).scalars().all()
        assert questions

        scoped_rules = db_session.execute(
            select(ObligationApplicabilityRule).where(
                ObligationApplicabilityRule.framework_id == framework.id,
                ObligationApplicabilityRule.rule_key.like("seeded_india_%"),
                ObligationApplicabilityRule.status == "active",
            )
        ).scalars().all()
        assert len(scoped_rules) == len(obligations) * len(questions) * 2

        for obligation in obligations:
            obligation_rules = [row for row in scoped_rules if row.obligation_id == obligation.id]
            assert obligation_rules
            yes_rules = [row for row in obligation_rules if row.expected_value_json is True]
            no_rules = [row for row in obligation_rules if row.expected_value_json is False]
            assert yes_rules and no_rules
            assert all(row.operator == "equals" for row in obligation_rules)
            assert all(row.result_applicability in {"applicable", "not_applicable"} for row in obligation_rules)


def test_india_first_pack_reseed_inactivates_removed_questions_and_archives_stale_seeded_rules(db_session):
    _seed_frameworks(db_session)

    certin = db_session.execute(select(Framework).where(Framework.code == "CERT_IN_2022")).scalar_one()
    certin_question = db_session.execute(
        select(ObligationApplicabilityQuestion).where(
            ObligationApplicabilityQuestion.framework_id == certin.id,
            ObligationApplicabilityQuestion.question_key == "operates_digital_systems_in_india",
            ObligationApplicabilityQuestion.organization_id.is_(None),
            ObligationApplicabilityQuestion.obligation_id.is_(None),
        )
    ).scalar_one()
    obligation = db_session.execute(
        select(Obligation).where(Obligation.framework_id == certin.id, Obligation.status == "active")
    ).scalars().first()
    assert obligation is not None

    stale_question = ObligationApplicabilityQuestion(
        organization_id=None,
        framework_id=certin.id,
        obligation_id=None,
        question_key="legacy_certin_question",
        question_text="Legacy seed question",
        help_text="legacy",
        answer_type="boolean",
        required=True,
        sort_order=99,
        status="active",
        metadata_json={"legacy": True},
    )
    db_session.add(stale_question)
    db_session.flush()

    stale_rule = ObligationApplicabilityRule(
        framework_id=certin.id,
        obligation_id=obligation.id,
        question_id=certin_question.id,
        rule_key="seeded_india_legacy_rule",
        operator="equals",
        expected_value_json=True,
        result_applicability="applicable",
        rationale="legacy",
        status="active",
        created_by_user_id=None,
    )
    db_session.add(stale_rule)
    db_session.commit()

    SeedService.ensure_india_first_pack_frameworks(db_session)
    db_session.commit()

    refreshed_legacy_question = db_session.get(ObligationApplicabilityQuestion, stale_question.id)
    assert refreshed_legacy_question is not None
    assert refreshed_legacy_question.status == "inactive"

    refreshed_legacy_rule = db_session.get(ObligationApplicabilityRule, stale_rule.id)
    assert refreshed_legacy_rule is not None
    assert refreshed_legacy_rule.status == "archived"
