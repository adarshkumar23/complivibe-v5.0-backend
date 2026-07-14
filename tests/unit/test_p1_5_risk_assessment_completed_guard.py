"""P1.5 regression: submit-responses must not silently mutate a COMPLETED AI
risk assessment. Previously re-submitting overwrote every response row while
the overall_risk_score (only computed by /complete) stayed frozen, leaving the
persisted score contradicting the persisted responses. A completed assessment
is immutable via submit-responses (409); scores can never go stale.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.ai_risk_assessment import AIRiskAssessment
from app.models.ai_risk_assessment_response import AIRiskAssessmentResponse
from app.models.ai_risk_assessment_question import AIRiskAssessmentQuestion
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"
RA_BASE = "/api/v1/ai-governance/risk-assessments"


def _system(client, headers, owner_id):
    r = client.post(
        f"{SYSTEMS_BASE}",
        headers=headers,
        json={"name": "Sys", "system_type": "model", "owner_id": owner_id, "deployment_status": "development", "risk_tier": "limited"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_completed_assessment_rejects_resubmit_and_keeps_score(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ra-guard")
    h = org["org_headers"]
    system_id = _system(client, h, org["user_id"])

    created = client.post(f"{SYSTEMS_BASE}/{system_id}/risk-assessments", headers=h)
    assert created.status_code == 201, created.text
    aid = created.json()["id"]

    rows = db_session.execute(
        select(AIRiskAssessmentResponse, AIRiskAssessmentQuestion)
        .join(AIRiskAssessmentQuestion, AIRiskAssessmentQuestion.id == AIRiskAssessmentResponse.question_id)
        .where(AIRiskAssessmentResponse.assessment_id == uuid.UUID(aid))
    ).all()
    assert rows, "expected seeded question/response rows"

    # Answer everything critical, then complete -> high score.
    payload = {"responses": [{"question_id": str(r.question_id), "response": "critical_risk"} for r, _q in rows]}
    assert client.post(f"{RA_BASE}/{aid}/submit-responses", headers=h, json=payload).status_code == 200
    completed = client.post(f"{RA_BASE}/{aid}/complete", headers=h)
    assert completed.status_code == 200, completed.text
    score_at_completion = completed.json()["overall_risk_score"]
    assert completed.json()["status"] == "completed"

    # Re-submit the exact opposite answers -> must be rejected, not silently applied.
    opposite = {"responses": [{"question_id": str(r.question_id), "response": "low_risk"} for r, _q in rows]}
    resubmit = client.post(f"{RA_BASE}/{aid}/submit-responses", headers=h, json=opposite)
    assert resubmit.status_code == 409, f"completed assessment must reject resubmit, got {resubmit.status_code}"

    # Score and responses unchanged (no stale/contradictory state).
    db_session.expire_all()
    assessment = db_session.get(AIRiskAssessment, uuid.UUID(aid))
    assert str(assessment.overall_risk_score) == str(score_at_completion).rstrip("0").rstrip(".") or \
        float(assessment.overall_risk_score) == float(score_at_completion)
    still = db_session.execute(
        select(AIRiskAssessmentResponse.response).where(AIRiskAssessmentResponse.assessment_id == uuid.UUID(aid))
    ).scalars().all()
    assert all(v == "critical_risk" for v in still), "responses must be unchanged after rejected resubmit"
