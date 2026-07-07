from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_risk_assessment_question import AIRiskAssessmentQuestion
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.ai_system import AISystem
from sqlalchemy import select
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


def test_risk_explanation_names_driving_dimensions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-risk-explain")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Explain System")

    created = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=org["org_headers"])
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    rows = db_session.execute(
        select(AIRiskAssessmentResponse, AIRiskAssessmentQuestion)
        .join(AIRiskAssessmentQuestion, AIRiskAssessmentQuestion.id == AIRiskAssessmentResponse.question_id)
        .where(AIRiskAssessmentResponse.assessment_id == uuid.UUID(assessment_id))
    ).all()

    # Answer everything low, except privacy which we push to critical_risk so
    # it should be named as the driver of the explanation.
    payload = {
        "responses": [
            {
                "question_id": str(resp.question_id),
                "response": "critical_risk" if question.risk_dimension == "privacy" else "low_risk",
            }
            for resp, question in rows
        ]
    }
    submit = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/submit-responses", headers=org["org_headers"], json=payload)
    assert submit.status_code == 200

    complete = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/complete", headers=org["org_headers"])
    assert complete.status_code == 200
    body = complete.json()

    # INTELLIGENT: must explain *why*, naming the privacy dimension and its rationale,
    # not just report privacy_risk_rating="critical" in isolation.
    assert body["privacy_risk_rating"] == "critical"
    assert body["risk_explanation"] is not None
    assert "privacy" in body["risk_explanation"].lower()
    assert body["reassessment_required"] is False
    assert body["ai_system_archived"] is False


def test_reassessment_required_after_system_attributes_change(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-risk-stale")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Stale System")

    created = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=org["org_headers"])
    assessment_id = created.json()["id"]
    rows = db_session.execute(
        select(AIRiskAssessmentResponse).where(AIRiskAssessmentResponse.assessment_id == uuid.UUID(assessment_id))
    ).scalars().all()
    payload = {"responses": [{"question_id": str(row.question_id), "response": "low_risk"} for row in rows]}
    client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/submit-responses", headers=org["org_headers"], json=payload)
    complete = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/complete", headers=org["org_headers"])
    assert complete.status_code == 200
    assert complete.json()["reassessment_required"] is False

    # CONTEXT-CONSCIOUS: simulate the AI system's registered attributes being
    # edited (e.g. new data types processed) strictly after the assessment
    # completed, by directly moving updated_at into the future -- the API's
    # PATCH endpoint stamps updated_at on every write, so this mirrors that.
    system_row = db_session.execute(
        select(AISystem).where(AISystem.id == uuid.UUID(system_id))
    ).scalar_one()
    system_row.updated_at = datetime.now(UTC) + timedelta(days=1)
    db_session.commit()

    fetched = client.get(f"{RISK_ASSESS_BASE}/{assessment_id}", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["reassessment_required"] is True


def test_assessment_survives_archived_ai_system(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g7-risk-archived")
    system_id = _create_system(client, org["org_headers"], org["user_id"], name="Archivable System")

    created = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=org["org_headers"])
    assessment_id = created.json()["id"]

    # Decommission + delete (soft-delete) the AI system.
    decommissioned = client.post(
        f"{SYSTEMS_BASE}/{system_id}/status", headers=org["org_headers"], json={"new_status": "decommissioned"}
    )
    assert decommissioned.status_code == 200
    deleted = client.delete(f"{SYSTEMS_BASE}/{system_id}", headers=org["org_headers"])
    assert deleted.status_code == 200

    # EDGE CASE: fetching the assessment must not crash just because its
    # AI system has since been archived.
    fetched = client.get(f"{RISK_ASSESS_BASE}/{assessment_id}", headers=org["org_headers"])
    assert fetched.status_code == 200
    assert fetched.json()["ai_system_archived"] is True
