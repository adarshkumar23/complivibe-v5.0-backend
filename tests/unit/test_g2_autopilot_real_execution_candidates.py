import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_risk_classification_phase64 import (
    ASSESSMENTS_BASE,
    _create_ai_system,
    _create_assessment,
)

STALE_DAYS = 31


def _persist_signals(client, headers: dict[str, str], assessment_id: str) -> None:
    resp = client.post(
        f"{ASSESSMENTS_BASE}/{assessment_id}/refresh-classification-signals",
        headers=headers,
        json={"persist_signals": True},
    )
    assert resp.status_code == 200, resp.text


def test_refresh_signals_candidate_is_generated_for_stale_assessment(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g2-refresh")
    ai = _create_ai_system(client, org["org_headers"], name="G2-Refresh-AI")
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="low")

    row = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    row.created_at = datetime.now(UTC) - timedelta(days=STALE_DAYS)
    row.updated_at = datetime.now(UTC) - timedelta(days=STALE_DAYS)
    db_session.commit()

    _persist_signals(client, org["org_headers"], assessment["id"])

    resp = client.get(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/candidate-actions",
        headers=org["org_headers"],
    )
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    action_types = {a["action_type"] for a in actions}
    assert "refresh_signals" in action_types, actions
    refresh_actions = [a for a in actions if a["action_type"] == "refresh_signals"]
    assert refresh_actions[0]["action_key"] == "refresh_stale_signals"


def test_attach_evidence_candidate_is_generated_for_missing_mitigation_on_high_risk(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g2-evidence")
    ai = _create_ai_system(client, org["org_headers"], name="G2-Evidence-AI")
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="high")

    _persist_signals(client, org["org_headers"], assessment["id"])

    resp = client.get(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/candidate-actions",
        headers=org["org_headers"],
    )
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    flag_actions = [a for a in actions if a["action_key"] == "flag_stale_evidence"]
    assert flag_actions, actions
    assert flag_actions[0]["action_type"] == "attach_evidence"


def test_send_reminder_candidate_is_generated_for_overdue_owner(client, db_session):
    org = bootstrap_org_user(client, email_prefix="g2-reminder")
    ai = _create_ai_system(client, org["org_headers"], name="G2-Reminder-AI")
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="low")

    row = db_session.get(AISystemRiskAssessment, uuid.UUID(assessment["id"]))
    row.owner_user_id = uuid.UUID(org["user_id"])
    row.created_at = datetime.now(UTC) - timedelta(days=STALE_DAYS)
    row.updated_at = datetime.now(UTC) - timedelta(days=STALE_DAYS)
    db_session.commit()

    _persist_signals(client, org["org_headers"], assessment["id"])

    resp = client.get(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/candidate-actions",
        headers=org["org_headers"],
    )
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    reminder_actions = [a for a in actions if a["action_type"] == "send_reminder"]
    assert reminder_actions, actions
    assert reminder_actions[0]["action_key"] == "send_reminder"
