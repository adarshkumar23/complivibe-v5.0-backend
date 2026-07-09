from __future__ import annotations

import uuid

from app.models.ai_risk_assessment_question import AIRiskAssessmentQuestion
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
RISK_ASSESS_BASE = "/api/v1/ai-governance/risk-assessments"
DIAGNOSTICS_BASE = "/api/v1/ai-governance/diagnostics"


def _create_system(client, headers, owner_id, name):
    resp = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "production",
            "risk_tier": "high",
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _complete_full_questionnaire(client, db_session, headers, system_id):
    created = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=headers)
    assert created.status_code == 201
    assessment_id = created.json()["id"]

    rows = (
        db_session.query(AIRiskAssessmentResponse, AIRiskAssessmentQuestion)
        .join(AIRiskAssessmentQuestion, AIRiskAssessmentQuestion.id == AIRiskAssessmentResponse.question_id)
        .filter(AIRiskAssessmentResponse.assessment_id == uuid.UUID(assessment_id))
        .all()
    )
    payload = {"responses": [{"question_id": str(resp.question_id), "response": "high_risk"} for resp, _q in rows]}
    submitted = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/submit-responses", headers=headers, json=payload)
    assert submitted.status_code == 200

    completed = client.post(f"{RISK_ASSESS_BASE}/{assessment_id}/complete", headers=headers)
    assert completed.status_code == 200
    return assessment_id


def test_completing_questionnaire_syncs_authoritative_table_and_clears_dashboard_warning(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g5aitab")
    headers = org["org_headers"]
    system_id = _create_system(client, headers, org["user_id"], "G5 Unification System")

    # Before completion: dashboard flags "no completed risk assessment".
    snapshot_before = client.post(f"{DIAGNOSTICS_BASE}/generate", headers=headers, json={})
    assert snapshot_before.status_code == 200
    system_summary_before = snapshot_before.json()["snapshot_data"]["ai_systems_summary"][0]
    assert system_summary_before["has_completed_risk_assessment"] is False
    assert "No completed risk assessment" in system_summary_before["governance_gaps"]

    _complete_full_questionnaire(client, db_session, headers, system_id)

    # The completion must be mirrored onto the authoritative ai_system_risk_assessments table.
    synced = (
        db_session.query(AISystemRiskAssessment)
        .filter(
            AISystemRiskAssessment.ai_system_id == uuid.UUID(system_id),
            AISystemRiskAssessment.status == "completed",
        )
        .one_or_none()
    )
    assert synced is not None
    assert synced.risk_dimensions_json["bias"] == "high"

    # After completion: the dashboard's "needs assessment" warning must clear.
    snapshot_after = client.post(f"{DIAGNOSTICS_BASE}/generate", headers=headers, json={})
    assert snapshot_after.status_code == 200
    system_summary_after = snapshot_after.json()["snapshot_data"]["ai_systems_summary"][0]
    assert system_summary_after["has_completed_risk_assessment"] is True
    assert "No completed risk assessment" not in system_summary_after["governance_gaps"]


def test_recommendation_engine_reads_from_authoritative_table(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g5aitab2")
    headers = org["org_headers"]
    system_id = _create_system(client, headers, org["user_id"], "G5 Recommendation System")

    _complete_full_questionnaire(client, db_session, headers, system_id)

    generated = client.post(f"{SYSTEMS_BASE}/{system_id}/generate-recommendations", headers=headers)
    assert generated.status_code == 200
    texts = [row["recommendation_text"] for row in generated.json()]
    # With every dimension answered "high_risk", bias-high template text must appear
    # (sourced from AISystemRiskAssessment.risk_dimensions_json, not the legacy table).
    assert any("bias testing" in text.lower() for text in texts)
