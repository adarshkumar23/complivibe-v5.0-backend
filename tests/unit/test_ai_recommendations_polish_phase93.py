from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.audit_log import AuditLog
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_signals_recs_diagnostics_a67_a68_a69 import RECOMMENDATIONS_BASE, SYSTEMS_BASE, _create_system


def _complete_assessment(db_session, assessment_id: str, *, bias_risk_rating: str = "high") -> AIRiskAssessment:
    row = db_session.execute(
        select(AIRiskAssessment).where(AIRiskAssessment.id == uuid.UUID(assessment_id))
    ).scalar_one()
    row.status = "completed"
    row.bias_risk_rating = bias_risk_rating
    row.completed_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    db_session.add(row)
    db_session.commit()
    return row


def test_phase93_recommendation_payload_context_and_apply_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p93-recs")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "P93 Recs")

    created_assessment = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=org["org_headers"])
    assert created_assessment.status_code == 201
    _complete_assessment(db_session, created_assessment.json()["id"])

    generated = client.post(f"{SYSTEMS_BASE}/{system_id}/generate-recommendations", headers=org["org_headers"])
    assert generated.status_code == 200
    rows = generated.json()
    assert rows

    first = rows[0]
    assert first["priority_weight"] in {1, 2, 3, 4}
    assert first["action_due_in_days"] > 0
    assert first["linked_task_count"] == 0
    assert "action_pending" in first["context_flags"]

    rec_id = first["id"]
    rec_row = db_session.execute(
        select(AIRiskAssessment).where(AIRiskAssessment.id == uuid.UUID(first["source_ref_id"]))
    ).scalar_one()
    rec_row.completed_at = datetime.now(UTC) - timedelta(days=45)
    rec_row.updated_at = datetime.now(UTC) + timedelta(minutes=5)
    db_session.add(rec_row)
    db_session.commit()

    listed = client.get(f"{SYSTEMS_BASE}/{system_id}/recommendations?status=active", headers=org["org_headers"])
    assert listed.status_code == 200
    refreshed = next(item for item in listed.json() if item["id"] == rec_id)
    assert refreshed["stale_source"] is True
    assert refreshed["source_age_days"] >= 45
    assert refreshed["source_updated_after_generation"] is True
    assert "stale_source" in refreshed["context_flags"]
    assert "source_updated_after_generation" in refreshed["context_flags"]

    applied = client.post(f"{RECOMMENDATIONS_BASE}/{rec_id}/apply", headers=org["org_headers"])
    assert applied.status_code == 200
    applied_body = applied.json()
    assert applied_body["status"] == "applied"
    assert applied_body["linked_task_count"] == 1
    assert "recommendation_applied" in applied_body["context_flags"]
    assert "task_linked" in applied_body["context_flags"]

    task_count = db_session.execute(
        select(Task).where(
            Task.organization_id == uuid.UUID(org["organization_id"]),
            Task.linked_entity_id == uuid.UUID(rec_id),
        )
    ).scalars().all()
    assert len(task_count) == 1

    audit_actions = {
        row.action
        for row in db_session.execute(
            select(AuditLog).where(
                AuditLog.organization_id == uuid.UUID(org["organization_id"]),
                AuditLog.entity_id == uuid.UUID(rec_id),
            )
        ).scalars()
    }
    assert "recommendation.applied" in audit_actions


def test_phase93_recommendation_edge_state_guards(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p93-recs-edge")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "P93 Recs Edge")

    created_assessment = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=org["org_headers"])
    assert created_assessment.status_code == 201
    _complete_assessment(db_session, created_assessment.json()["id"])

    generated = client.post(f"{SYSTEMS_BASE}/{system_id}/generate-recommendations", headers=org["org_headers"])
    assert generated.status_code == 200
    recs = generated.json()
    assert len(recs) >= 2

    manual_task = Task(
        organization_id=uuid.UUID(org["organization_id"]),
        title="Existing linked task",
        description="Inserted for guard test",
        status="open",
        priority="high",
        task_type="risk_treatment",
        owner_user_id=uuid.UUID(org["user_id"]),
        created_by_user_id=uuid.UUID(org["user_id"]),
        linked_entity_type="general",
        linked_entity_id=uuid.UUID(recs[0]["id"]),
        source="system",
        reminder_status="none",
        metadata_json={"seed": "phase93"},
    )
    db_session.add(manual_task)
    db_session.commit()

    apply_with_existing_task = client.post(f"{RECOMMENDATIONS_BASE}/{recs[0]['id']}/apply", headers=org["org_headers"])
    assert apply_with_existing_task.status_code == 422

    dismissed = client.post(f"{RECOMMENDATIONS_BASE}/{recs[1]['id']}/dismiss", headers=org["org_headers"])
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    dismiss_again = client.post(f"{RECOMMENDATIONS_BASE}/{recs[1]['id']}/dismiss", headers=org["org_headers"])
    assert dismiss_again.status_code == 422

    apply_dismissed = client.post(f"{RECOMMENDATIONS_BASE}/{recs[1]['id']}/apply", headers=org["org_headers"])
    assert apply_dismissed.status_code == 422
