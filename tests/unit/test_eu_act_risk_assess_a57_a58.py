from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


SYSTEMS_BASE = "/api/v1/ai-governance/systems"
RISK_ASSESS_BASE = "/api/v1/ai-governance/risk-assessments"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str = "AI System") -> str:
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


def test_a57_eu_act_workflows(client):
    org = bootstrap_org_user(client, email_prefix="a57-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="EU Workflow System")

    # Create conformity assessment and verify checklist pre-population.
    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment",
        headers=org["org_headers"],
        json={"assessment_type": "self_assessment"},
    )
    assert created.status_code == 201
    checklist = created.json()["checklist_items"]
    assert len(checklist) == 8
    assert all(item["completed"] is False for item in checklist)

    # Complete one item.
    item_key = checklist[0]["key"]
    complete_item = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment/complete-item",
        headers=org["org_headers"],
        json={"item_key": item_key},
    )
    assert complete_item.status_code == 200
    reloaded = complete_item.json()["checklist_items"]
    matched = [item for item in reloaded if item["key"] == item_key]
    assert len(matched) == 1
    assert matched[0]["completed"] is True

    # Cannot mark complete while unchecked items remain.
    blocked = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment/complete",
        headers=org["org_headers"],
    )
    assert blocked.status_code == 422

    # Complete all checklist items and finish.
    for item in reloaded:
        client.post(
            f"{SYSTEMS_BASE}/{system_id}/conformity-assessment/complete-item",
            headers=org["org_headers"],
            json={"item_key": item["key"]},
        )
    completed = client.post(
        f"{SYSTEMS_BASE}/{system_id}/conformity-assessment/complete",
        headers=org["org_headers"],
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "complete"

    # FRIA create + update + complete.
    fria_create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/fria",
        headers=org["org_headers"],
        json={"rights_affected": ["privacy", "non_discrimination"]},
    )
    assert fria_create.status_code == 201

    fria_update = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/fria",
        headers=org["org_headers"],
        json={"risk_to_rights_assessment": "Medium impact", "consultation_conducted": True},
    )
    assert fria_update.status_code == 200
    assert fria_update.json()["status"] == "in_progress"

    fria_complete = client.post(
        f"{SYSTEMS_BASE}/{system_id}/fria/complete",
        headers=org["org_headers"],
    )
    assert fria_complete.status_code == 200
    assert fria_complete.json()["status"] == "complete"

    # Post-market plan create + activate.
    plan_create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/post-market-plan",
        headers=org["org_headers"],
        json={
            "monitoring_metrics": [{"metric": "incident_rate", "threshold": "<2%"}],
            "reporting_frequency": "monthly",
            "responsible_person_id": org["user_id"],
        },
    )
    assert plan_create.status_code == 201

    plan_activate = client.post(
        f"{SYSTEMS_BASE}/{system_id}/post-market-plan/activate",
        headers=org["org_headers"],
    )
    assert plan_activate.status_code == 200
    assert plan_activate.json()["status"] == "active"


def test_a58_ai_risk_assessment_workflow(client, db_session, monkeypatch):
    org = bootstrap_org_user(client, email_prefix="a58-org")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Risk Assess System")

    # Create assessment => 30 pre-populated response rows.
    created = client.post(
        f"{SYSTEMS_BASE}/{system_id}/risk-assessments",
        headers=org["org_headers"],
    )
    assert created.status_code == 201
    assessment_id = created.json()["id"]
    assert created.json()["assessment_version"] == 1

    response_count = db_session.execute(
        select(func.count(AIRiskAssessmentResponse.id)).where(
            AIRiskAssessmentResponse.organization_id == uuid.UUID(org["organization_id"]),
            AIRiskAssessmentResponse.assessment_id == uuid.UUID(assessment_id),
        )
    ).scalar_one()
    assert int(response_count) == 30

    # Submit subset => in_progress.
    rows = db_session.execute(
        select(AIRiskAssessmentResponse).where(
            AIRiskAssessmentResponse.organization_id == uuid.UUID(org["organization_id"]),
            AIRiskAssessmentResponse.assessment_id == uuid.UUID(assessment_id),
        )
    ).scalars().all()
    partial_payload = {
        "responses": [
            {"question_id": str(rows[0].question_id), "response": "high_risk", "notes": "partial fill"},
            {"question_id": str(rows[1].question_id), "response": "medium_risk", "notes": "partial fill"},
        ]
    }
    partial = client.post(
        f"{RISK_ASSESS_BASE}/{assessment_id}/submit-responses",
        headers=org["org_headers"],
        json=partial_payload,
    )
    assert partial.status_code == 200
    assert partial.json()["status"] == "in_progress"

    # Cannot complete with unanswered questions.
    blocked_complete = client.post(
        f"{RISK_ASSESS_BASE}/{assessment_id}/complete",
        headers=org["org_headers"],
    )
    assert blocked_complete.status_code == 422

    # Fill all remaining and complete.
    full_payload = {
        "responses": [
            {"question_id": str(row.question_id), "response": "critical_risk", "notes": "filled"}
            for row in rows
        ]
    }
    full_submit = client.post(
        f"{RISK_ASSESS_BASE}/{assessment_id}/submit-responses",
        headers=org["org_headers"],
        json=full_payload,
    )
    assert full_submit.status_code == 200

    completed = client.post(
        f"{RISK_ASSESS_BASE}/{assessment_id}/complete",
        headers=org["org_headers"],
    )
    assert completed.status_code == 200
    body = completed.json()
    assert body["status"] == "completed"
    assert 0 <= float(body["overall_risk_score"]) <= 100
    assert body["bias_risk_rating"] in {"low", "medium", "high", "critical"}

    # Risk record auto-created.
    created_risk = db_session.execute(
        select(Risk).where(
            Risk.organization_id == uuid.UUID(org["organization_id"]),
            Risk.metadata_json.is_not(None),
            Risk.title.ilike("AI Risk:%"),
        )
    ).scalars().first()
    assert created_risk is not None

    # Version auto-increments.
    created_v2 = client.post(
        f"{SYSTEMS_BASE}/{system_id}/risk-assessments",
        headers=org["org_headers"],
    )
    assert created_v2.status_code == 201
    assert created_v2.json()["assessment_version"] == 2

    # compute_bias mocked (no actual ML call).
    from app.ai_governance.services.bias_metrics_service import BiasMetricsService

    monkeypatch.setattr(
        BiasMetricsService,
        "compute_bias_metrics",
        staticmethod(lambda predictions, protected_attribute_values, labels=None: {"demographic_parity_ratio": 0.92}),
    )
    bias = client.post(
        f"{RISK_ASSESS_BASE}/{assessment_id}/compute-bias",
        headers=org["org_headers"],
        json={
            "predictions": [1, 0, 1, 1],
            "protected_attribute_values": [1, 0, 1, 0],
        },
    )
    assert bias.status_code == 200
    assert "demographic_parity_ratio" in bias.json()

    # Org isolation.
    org_b = bootstrap_org_user(client, email_prefix="a58-org-b")
    forbidden = client.get(
        f"{RISK_ASSESS_BASE}/{assessment_id}",
        headers=org_b["org_headers"],
    )
    assert forbidden.status_code == 404

    # Score bounds are decimals in range.
    row = db_session.execute(
        select(AIRiskAssessment).where(AIRiskAssessment.id == uuid.UUID(assessment_id))
    ).scalar_one()
    assert row.overall_risk_score is not None
    assert Decimal("0") <= row.overall_risk_score <= Decimal("100")
