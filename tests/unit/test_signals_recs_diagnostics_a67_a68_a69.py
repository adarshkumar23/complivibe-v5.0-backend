from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.ai_governance.services.signal_service import SignalService
from app.models.ai_risk_assessment_question import AIRiskAssessmentQuestion
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
RISK_SIGNALS_BASE = "/api/v1/ai-governance/risk-signals"
RECOMMENDATIONS_BASE = "/api/v1/ai-governance/recommendations"
EVENTS_BASE = "/api/v1/ai-governance/events"
RISK_ASSESS_BASE = "/api/v1/ai-governance/risk-assessments"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str) -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": "limited",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_a67_risk_signals(db_session, client):
    org = bootstrap_org_user(client, email_prefix="a67-org")
    org_id = uuid.UUID(org["organization_id"])
    system_id = uuid.UUID(_create_system(client, org["org_headers"], org["user_id"], "A67 System"))

    service = SignalService(db_session)

    created = service.emit_signal(
        org_id,
        system_id,
        signal_type="new_use_case",
        description="Production rollout to external users",
        actor_id=uuid.UUID(org["user_id"]),
    )
    assert created is not None
    assert created.severity == "critical"

    deduped = service.emit_signal(
        org_id,
        system_id,
        signal_type="new_use_case",
        description="Production rollout to external users",
        actor_id=uuid.UUID(org["user_id"]),
    )
    assert deduped is not None
    assert deduped.id == created.id

    low = service.emit_signal(
        org_id,
        system_id,
        signal_type="model_version_change",
        description="Minor update with no contextual keywords",
        actor_id=uuid.UUID(org["user_id"]),
    )
    assert low is not None
    assert low.severity == "low"

    reviewed = service.review_signal(
        org_id,
        created.id,
        action="acknowledge",
        reviewer_id=uuid.UUID(org["user_id"]),
        notes="Checked",
    )
    assert reviewed.status == "reviewed"

    db_session.commit()

    # Hook: status update emits deployment_scope_expansion signal.
    status_change = client.post(
        f"{SYSTEMS_BASE}/{system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "production"},
    )
    assert status_change.status_code == 200

    signals = client.get(f"{SYSTEMS_BASE}/{system_id}/risk-signals", headers=org["org_headers"])
    assert signals.status_code == 200
    signal_types = {row["signal_type"] for row in signals.json()}
    assert "deployment_scope_expansion" in signal_types

    # Hook: AIBOM training_data component emits new_training_data_source signal.
    create_aibom = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom",
        headers=org["org_headers"],
        json={"notes": "a67"},
    )
    assert create_aibom.status_code == 201

    add_training_data = client.post(
        f"{SYSTEMS_BASE}/{system_id}/aibom/components",
        headers=org["org_headers"],
        json={
            "component_type": "training_data",
            "name": "new-dataset-source",
            "version": "1",
        },
    )
    assert add_training_data.status_code == 201

    signals_after = client.get(f"{SYSTEMS_BASE}/{system_id}/risk-signals", headers=org["org_headers"])
    assert signals_after.status_code == 200
    signal_types_after = {row["signal_type"] for row in signals_after.json()}
    assert "new_training_data_source" in signal_types_after


def test_a68_recommendations_and_apply_dismiss(db_session, client):
    org = bootstrap_org_user(client, email_prefix="a68-org")
    org_id = uuid.UUID(org["organization_id"])
    system_id = _create_system(client, org["org_headers"], org["user_id"], "A68 System")
    system_uuid = uuid.UUID(system_id)

    # Create assessment, then answer real questions to force bias=high (and every
    # other dimension low) for deterministic template selection, and complete it
    # through the real service (not a DB shortcut) so the completion is mirrored
    # onto ai_system_risk_assessments the same way production traffic is.
    created_assessment = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=org["org_headers"])
    assert created_assessment.status_code == 201
    assessment_id = uuid.UUID(created_assessment.json()["id"])

    response_rows = (
        db_session.query(AIRiskAssessmentResponse, AIRiskAssessmentQuestion)
        .join(AIRiskAssessmentQuestion, AIRiskAssessmentQuestion.id == AIRiskAssessmentResponse.question_id)
        .filter(AIRiskAssessmentResponse.assessment_id == assessment_id)
        .all()
    )
    payload = {
        "responses": [
            {
                "question_id": str(resp.question_id),
                "response": "high_risk" if question.risk_dimension == "bias" else "low_risk",
            }
            for resp, question in response_rows
        ]
    }
    submitted = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/submit-responses", headers=org["org_headers"], json=payload)
    assert submitted.status_code == 200

    completed = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/complete", headers=org["org_headers"])
    assert completed.status_code == 200
    assert completed.json()["bias_risk_rating"] == "high"

    generated = client.post(f"{SYSTEMS_BASE}/{system_id}/generate-recommendations", headers=org["org_headers"])
    assert generated.status_code == 200
    generated_payload = generated.json()
    assert any("Conduct bias testing across all protected attributes" in row["recommendation_text"] for row in generated_payload)

    # Idempotent generation does not create duplicates.
    generated_again = client.post(f"{SYSTEMS_BASE}/{system_id}/generate-recommendations", headers=org["org_headers"])
    assert generated_again.status_code == 200

    listed = client.get(f"{SYSTEMS_BASE}/{system_id}/recommendations?status=active", headers=org["org_headers"])
    assert listed.status_code == 200
    texts = [row["recommendation_text"] for row in listed.json()]
    assert len(texts) == len(set(texts))

    # No completed assessment -> generic recommendations.
    system_without_assessment = _create_system(client, org["org_headers"], org["user_id"], "A68 Generic System")
    generic_generated = client.post(
        f"{SYSTEMS_BASE}/{system_without_assessment}/generate-recommendations",
        headers=org["org_headers"],
    )
    assert generic_generated.status_code == 200
    assert any("Review AI risk assessment results with the system owner" in row["recommendation_text"] for row in generic_generated.json())

    # Apply recommendation creates task and marks applied.
    rec_id = listed.json()[0]["id"]
    applied = client.post(f"{RECOMMENDATIONS_BASE}/{rec_id}/apply", headers=org["org_headers"])
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"

    task = db_session.query(Task).filter(
        Task.organization_id == org_id,
        Task.linked_entity_id == uuid.UUID(rec_id),
    ).order_by(Task.created_at.desc()).first()
    assert task is not None
    assert task.description is not None
    assert "These are suggestions for human review, not compliance determinations." in task.description

    # Dismiss recommendation and block apply after dismissed.
    dismiss_target = listed.json()[-1]["id"]
    dismissed = client.post(f"{RECOMMENDATIONS_BASE}/{dismiss_target}/dismiss", headers=org["org_headers"])
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    apply_dismissed = client.post(f"{RECOMMENDATIONS_BASE}/{dismiss_target}/apply", headers=org["org_headers"])
    assert apply_dismissed.status_code == 422


def test_a69_diagnostics_event_log_and_summary(client):
    org = bootstrap_org_user(client, email_prefix="a69-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "A69 System")

    # Generate event rows.
    status_change = client.post(
        f"{SYSTEMS_BASE}/{system_id}/status",
        headers=org["org_headers"],
        json={"new_status": "staging"},
    )
    assert status_change.status_code == 200

    # System events endpoint.
    system_events = client.get(f"{SYSTEMS_BASE}/{system_id}/event-log", headers=org["org_headers"])
    assert system_events.status_code == 200
    assert len(system_events.json()) >= 1

    # Org events with date filter.
    now = datetime.now(UTC)
    from_date = (now - timedelta(days=1)).isoformat()
    to_date = (now + timedelta(days=1)).isoformat()
    org_events = client.get(
        EVENTS_BASE,
        headers=org["org_headers"],
        params={"from_date": from_date, "to_date": to_date},
    )
    assert org_events.status_code == 200
    assert len(org_events.json()) >= 1

    summary = client.get(f"{EVENTS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_events_30d"] >= 1
    assert isinstance(payload["by_event_type"], dict)

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a69-org-b")
    org_b_events = client.get(EVENTS_BASE, headers=org_b["org_headers"])
    assert org_b_events.status_code == 200
    # B should not see A's events for A's system.
    assert all(row.get("ai_system_id") != system_id for row in org_b_events.json())

    # Diagnostics is read-only.
    not_allowed = client.post(EVENTS_BASE, headers=org["org_headers"], json={})
    assert not_allowed.status_code == 405
