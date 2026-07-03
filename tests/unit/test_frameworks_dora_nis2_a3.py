from __future__ import annotations

from uuid import UUID

from sqlalchemy import inspect, select

from app.compliance.services.incident_sla_service import DORA_SLA_HOURS, NIS2_SLA_HOURS
from app.models.breach_notification import BreachNotification
from app.models.cross_framework_obligation_mapping import CrossFrameworkObligationMapping
from app.models.dora_ict_register import DORAICTRegister
from app.models.framework import Framework
from app.models.framework_section import FrameworkSection
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


def _create_issue(client, org_headers: dict, owner_id: str, *, issue_type: str = "security_incident") -> dict:
    response = client.post(
        "/api/v1/compliance/issues",
        headers=org_headers,
        json={
            "title": "A3 issue",
            "description": "A3 issue description",
            "issue_type": issue_type,
            "severity": "high",
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_dora_framework_seeded_and_table_exists(db_session):
    _seed_frameworks(db_session)
    dora = _framework(db_session, "DORA")

    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == dora.id)).scalars().all()
    sections = db_session.execute(select(FrameworkSection).where(FrameworkSection.framework_id == dora.id)).scalars().all()

    assert len(obligations) >= 20
    assert len(sections) == 5

    tables = set(inspect(db_session.bind).get_table_names())
    assert "dora_ict_register" in tables


def test_dora_ict_register_crud_and_report(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a3-dora")
    _seed_frameworks(db_session)

    create_resp = client.post(
        "/api/v1/compliance/dora/ict-register",
        headers=org["org_headers"],
        json={
            "counterparty_name": "Provider A",
            "service_description": "Cloud core banking workload",
            "is_critical_function": True,
            "sub_outsourcing_used": True,
            "data_location": "DE",
            "data_location_countries": ["DE", "FR"],
            "exit_strategy_documented": False,
            "owner_id": org["user_id"],
            "status": "active",
        },
    )
    assert create_resp.status_code == 201
    entry = create_resp.json()

    db_row = db_session.get(DORAICTRegister, UUID(entry["id"]))
    assert db_row is not None
    assert db_row.counterparty_name == "Provider A"

    report_resp = client.get("/api/v1/compliance/dora/ict-register/report", headers=org["org_headers"])
    assert report_resp.status_code == 200
    report = report_resp.json()
    assert set(report.keys()) == {
        "total_providers",
        "critical_function_count",
        "missing_exit_strategy",
        "assessment_overdue",
        "by_data_location",
        "sub_outsourcing_count",
    }
    assert report["missing_exit_strategy"] >= 1

    delete_resp = client.delete(f"/api/v1/compliance/dora/ict-register/{entry['id']}", headers=org["org_headers"])
    assert delete_resp.status_code == 200
    deleted = db_session.get(DORAICTRegister, UUID(entry["id"]))
    assert deleted is not None
    assert deleted.deleted_at is not None


def test_nis2_framework_seeded_and_applicability(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a3-nis2")
    _seed_frameworks(db_session)
    nis2 = _framework(db_session, "NIS2")

    obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == nis2.id)).scalars().all()
    sections = db_session.execute(select(FrameworkSection).where(FrameworkSection.framework_id == nis2.id)).scalars().all()
    assert len(obligations) >= 14
    assert len(sections) == 3

    questions_resp = client.get(f"/api/v1/compliance/frameworks/{nis2.id}/applicability-questions", headers=org["org_headers"])
    assert questions_resp.status_code == 200
    keys = {row["question_key"] for row in questions_resp.json()}
    assert "eu_entity" in keys

    assess_resp = client.post(
        f"/api/v1/compliance/frameworks/{nis2.id}/assess-applicability",
        headers=org["org_headers"],
        json={"answers": {"eu_entity": True, "entity_type": True, "sector": "energy"}},
    )
    assert assess_resp.status_code == 200
    assert assess_resp.json()["applicable_obligation_count"] >= 14


def test_sla_wiring_and_regulatory_framework_storage(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a3-sla")

    assert DORA_SLA_HOURS["early_warning"] == 4
    assert NIS2_SLA_HOURS["early_warning"] == 24

    columns = {col["name"]: col for col in inspect(db_session.bind).get_columns("breach_notifications")}
    assert "regulatory_framework" in columns
    assert columns["regulatory_framework"]["nullable"] is True

    issue = _create_issue(client, org["org_headers"], org["user_id"])
    breach_resp = client.post(
        f"/api/v1/compliance/issues/{issue['id']}/breach-notification",
        headers=org["org_headers"],
        json={
            "breach_type": "personal_data",
            "personal_data_affected": True,
            "regulatory_notification_required": True,
            "regulatory_framework": "dora",
            "regulatory_notification_hours": 72,
        },
    )
    assert breach_resp.status_code == 201
    payload = breach_resp.json()
    assert payload["regulatory_framework"] == "dora"
    assert payload["regulatory_notification_hours"] == 4

    row = db_session.execute(select(BreachNotification).where(BreachNotification.id == UUID(payload["id"]))).scalar_one()
    assert row.regulatory_framework == "dora"


def test_cross_mappings_seeded_for_dora(client, db_session):
    org = bootstrap_org_user(client, email_prefix="a3-map")
    _seed_frameworks(db_session)

    dora = _framework(db_session, "DORA")
    dora_obligations = db_session.execute(select(Obligation).where(Obligation.framework_id == dora.id)).scalars().all()
    dora_ids = {row.id for row in dora_obligations}

    mappings = db_session.execute(select(CrossFrameworkObligationMapping)).scalars().all()
    dora_related = [row for row in mappings if row.source_obligation_id in dora_ids]
    assert len(dora_related) >= 3

    sample = next(item for item in dora_obligations if item.reference_code == "DORA-19.1")
    response = client.get(f"/api/v1/compliance/obligations/{sample.id}/cross-mappings", headers=org["org_headers"])
    assert response.status_code == 200
    targets = {item["target_reference_code"] for item in response.json()}
    assert "NIS2-23.2" in targets
