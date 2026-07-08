from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.eu_act_conformity_assessment import EUActConformityAssessment
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_eu_act_risk_assess_a57_a58 import SYSTEMS_BASE, _create_system


def test_phase90_conformity_reads_include_progress_context_and_stale_flags(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-conformity")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="P90 Conformity")

    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment",
        headers=org["org_headers"],
        json={"assessment_type": "self_assessment"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["checklist_total_items"] == 8
    assert body["checklist_completed_items"] == 0
    assert body["checklist_completion_percent"] == 0
    assert "checklist_incomplete" in body["context_flags"]
    assert body["stale_workflow"] is False

    row = db_session.execute(
        select(EUActConformityAssessment).where(EUActConformityAssessment.ai_system_id == uuid.UUID(system_id))
    ).scalar_one()
    row.updated_at = datetime.now(UTC) - timedelta(days=45)
    db_session.add(row)
    db_session.commit()

    stale = client.get(f"{SYSTEMS_BASE}/{system_id}/conformity-assessment", headers=org["org_headers"])
    assert stale.status_code == 200
    sbody = stale.json()
    assert sbody["stale_workflow"] is True
    assert "stale_workflow" in sbody["context_flags"]

    # Marking complete should fail until the required quality gates are met.
    blocked = client.post(f"{SYSTEMS_BASE}/{system_id}/conformity-assessment/complete", headers=org["org_headers"])
    assert blocked.status_code == 422


def test_phase90_fria_plan_guards_and_audit_actions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p90-fria-plan")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="P90 FRIA Plan")

    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment",
        headers=org["org_headers"],
        json={"assessment_type": "self_assessment"},
    )
    assert created.status_code == 201
    first_item = created.json()["checklist_items"][0]["key"]
    complete_one = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment/complete-item",
        headers=org["org_headers"],
        json={"item_key": first_item},
    )
    assert complete_one.status_code == 200
    assert complete_one.json()["checklist_completed_items"] == 1

    # FRIA: completion blocked until required narrative fields are present.
    fria_create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/fria",
        headers=org["org_headers"],
        json={"rights_affected": ["privacy"]},
    )
    assert fria_create.status_code == 201
    fria_blocked = client.post(f"{SYSTEMS_BASE}/{system_id}/fria/complete", headers=org["org_headers"])
    assert fria_blocked.status_code == 422

    fria_update = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/fria",
        headers=org["org_headers"],
        json={
            "risk_to_rights_assessment": "High impact on privacy rights",
            "mitigation_measures": "Independent review before each release",
            "consultation_conducted": True,
        },
    )
    assert fria_update.status_code == 200
    assert fria_update.json()["completeness_percent"] >= 75

    fria_complete = client.post(f"{SYSTEMS_BASE}/{system_id}/fria/complete", headers=org["org_headers"])
    assert fria_complete.status_code == 200
    assert fria_complete.json()["status"] == "complete"
    assert "workflow_complete" in fria_complete.json()["context_flags"]

    # Post-market plan: activation blocked when required fields become missing.
    plan_create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/post-market-plan",
        headers=org["org_headers"],
        json={
            "monitoring_metrics": [{"metric": "incident_rate", "threshold": "<2%"}],
            "reporting_frequency": "monthly",
            "incident_reporting_threshold": "Immediate escalation for severe incidents",
            "responsible_person_id": org["user_id"],
        },
    )
    assert plan_create.status_code == 201

    wipe_metrics = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/post-market-plan",
        headers=org["org_headers"],
        json={"monitoring_metrics": []},
    )
    assert wipe_metrics.status_code == 200

    blocked_activate = client.post(f"{SYSTEMS_BASE}/{system_id}/post-market-plan/activate", headers=org["org_headers"])
    assert blocked_activate.status_code == 422

    actions = {
        row.action
        for row in db_session.execute(
            select(AuditLog).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.action.like("eu_act.%"),
            )
        ).scalars()
    }
    assert "eu_act.conformity_item_completed" in actions
    assert "eu_act.fria_updated" in actions
    assert "eu_act.post_market_updated" in actions
