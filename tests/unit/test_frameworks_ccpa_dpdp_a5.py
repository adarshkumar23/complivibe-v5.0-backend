from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.models.consent_record import ConsentRecord
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.data_subject_request import DataSubjectRequest
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
from app.models.obligation import Obligation
from app.models.organization import Organization
from app.services.seed_service import SeedService
from tests.helpers.auth_org import bootstrap_org_user


CCPA_OPT_OUT_BASE = "/api/v1/privacy/ccpa/opt-out"


def _seed_frameworks(db_session) -> None:
    SeedService.ensure_framework_catalog(db_session)
    SeedService.ensure_framework_versions(db_session)
    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()


def _framework(db_session, name: str) -> Framework:
    row = db_session.execute(select(Framework).where(Framework.name == name)).scalar_one_or_none()
    assert row is not None
    return row


def test_ccpa_framework_seed_optout_and_annual_report(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a5-ccpa")
    _seed_frameworks(db_session)
    org_me = client.get("/api/v1/organizations/me", headers=org["headers"])
    assert org_me.status_code == 200
    org_slug = org_me.json()[0]["slug"]

    framework = _framework(db_session, "CCPA/CPRA")
    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
    sections = db_session.execute(select(FrameworkSection).where(FrameworkSection.framework_id == framework.id)).scalars().all()
    assert len(obligations) >= 15
    assert len(sections) == 3

    questions_resp = client.get(
        f"/api/v1/compliance/frameworks/{framework.id}/applicability-questions",
        headers=org["org_headers"],
    )
    assert questions_resp.status_code == 200
    qkeys = {row["question_key"] for row in questions_resp.json()}
    assert {"california_business", "meets_threshold", "sells_shares_pi"}.issubset(qkeys)

    invalid = client.post(
        CCPA_OPT_OUT_BASE,
        json={"subject_email": "bad@example.com", "subject_name": "Bad", "org_slug": "does-not-exist"},
    )
    assert invalid.status_code == 404

    opt_out = client.post(
        CCPA_OPT_OUT_BASE,
        json={"subject_email": "user@example.com", "subject_name": "Jane Smith", "org_slug": org_slug},
    )
    assert opt_out.status_code == 201
    payload = opt_out.json()
    assert "request_ref" in payload
    assert payload["message"] == "Opt-out request received. We will process within 15 business days."

    dsr_row = db_session.execute(
        select(DataSubjectRequest).where(
            DataSubjectRequest.organization_id == UUID(org["organization_id"]),
            DataSubjectRequest.request_ref == payload["request_ref"],
        )
    ).scalar_one_or_none()
    assert dsr_row is not None
    assert dsr_row.request_type == "opt_out_of_sale"
    assert dsr_row.regulatory_framework == "ccpa"
    assert dsr_row.deadline_days == 15

    consent_row = db_session.execute(
        select(ConsentRecord).where(
            ConsentRecord.organization_id == UUID(org["organization_id"]),
            ConsentRecord.subject_identifier_hash.is_not(None),
            ConsentRecord.consent_mechanism == "ccpa_opt_out",
        )
    ).scalars().first()
    assert consent_row is not None
    assert consent_row.granted is False

    # Add more CCPA requests to validate report structure/count keys.
    for request_type in ["access", "erasure", "rectification", "limit_sensitive"]:
        create_resp = client.post(
            "/api/v1/privacy/dsr",
            headers=org["org_headers"],
            json={
                "request_type": request_type,
                "subject_name": f"{request_type} user",
                "subject_email": f"{request_type}@example.com",
                "regulatory_framework": "ccpa",
            },
        )
        assert create_resp.status_code == 201

    report_resp = client.get("/api/v1/compliance/reports/regulatory/ccpa", headers=org["org_headers"])
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert report["report_type"] == "ccpa_annual"
    assert set(report["requests_received"].keys()) == {"know", "delete", "opt_out", "correct", "limit_sensitive"}
    assert set(report["response_metrics"].keys()) == {"within_deadline", "avg_response_days", "total_fulfilled"}


def test_dpdp_framework_sdf_columns_mappings_and_idempotent_seed(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a5-dpdp")
    _seed_frameworks(db_session)

    framework = _framework(db_session, "India DPDP")
    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
    sections = db_session.execute(select(FrameworkSection).where(FrameworkSection.framework_id == framework.id)).scalars().all()
    assert len(obligations) >= 18
    assert len(sections) == 4

    columns = {col["name"]: col for col in inspect(db_session.bind).get_columns("organizations")}
    assert "is_significant_data_fiduciary" in columns
    assert "sdf_category" in columns
    assert columns["is_significant_data_fiduciary"]["nullable"] is False

    org_update = client.patch(
        f"/api/v1/organizations/{org['organization_id']}",
        headers=org["org_headers"],
        json={"is_significant_data_fiduciary": True, "sdf_category": "critical_digital_service"},
    )
    assert org_update.status_code == 200
    updated_org = org_update.json()["organization"]
    assert updated_org["is_significant_data_fiduciary"] is True
    assert updated_org["sdf_category"] == "critical_digital_service"

    org_row = db_session.get(Organization, UUID(org["organization_id"]))
    assert org_row is not None
    assert org_row.is_significant_data_fiduciary is True

    dpdp_ids = {row.id for row in obligations}
    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    dpdp_related = [row for row in mappings if row.source_obligation_id in dpdp_ids]
    assert len(dpdp_related) >= 5

    source = next(row for row in obligations if row.reference_code == "DPDP-S4")
    map_resp = client.get(f"/api/v1/compliance/obligations/{source.id}/cross-mappings", headers=org["org_headers"])
    assert map_resp.status_code == 200
    assert len(map_resp.json()) >= 1

    before = db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
    before_refs = [row.reference_code for row in before]

    SeedService.ensure_starter_obligations(db_session)
    db_session.commit()

    after = db_session.execute(select(Obligation).where(Obligation.framework_id == framework.id)).scalars().all()
    after_refs = [row.reference_code for row in after]
    assert len(after_refs) == len(set(after_refs))
    assert len(after_refs) == len(before_refs)
