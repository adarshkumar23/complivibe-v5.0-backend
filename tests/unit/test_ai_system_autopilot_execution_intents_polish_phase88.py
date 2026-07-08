from datetime import UTC, datetime, timedelta
import uuid

from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_execution_intents_phase71 import INTENTS_BASE
from tests.unit.test_ai_system_autopilot_policies_phase70 import (
    POLICY_BASE,
    _create_recommendation_snapshot,
    _first_candidate_action,
    _seed,
)


def test_phase88_create_execution_intent_rejects_conflicting_source_fields(client):
    org = bootstrap_org_user(client, email_prefix="p88-invalid-combos")
    _, assessment, _ = _seed(client, org["org_headers"], name="P88-Invalid")
    candidate = _first_candidate_action(client, org["org_headers"], assessment_id=assessment["id"])
    recommendation_snapshot = _create_recommendation_snapshot(client, org["org_headers"], assessment_id=assessment["id"])

    bad_candidate = client.post(
        INTENTS_BASE,
        headers=org["org_headers"],
        json={
            "source_type": "candidate_action",
            "source_id": str(uuid.uuid4()),
            "candidate_action_json": candidate,
        },
    )
    assert bad_candidate.status_code == 400
    assert "source_id must be omitted" in bad_candidate.json()["detail"]

    bad_recommendation = client.post(
        INTENTS_BASE,
        headers=org["org_headers"],
        json={
            "source_type": "recommendation_snapshot",
            "source_id": recommendation_snapshot["id"],
            "candidate_action_json": candidate,
        },
    )
    assert bad_recommendation.status_code == 400
    assert "candidate_action_json is only allowed" in bad_recommendation.json()["detail"]


def test_phase88_execution_intents_expose_staleness_context_and_summary_intelligence(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p88-intent-context")
    _, assessment, _ = _seed(client, org["org_headers"], name="P88-Context")
    recommendation_snapshot = _create_recommendation_snapshot(client, org["org_headers"], assessment_id=assessment["id"])

    policy = client.post(
        POLICY_BASE,
        headers=org["org_headers"],
        json={
            "name": "p88-policy",
            "mode": "require_approval",
            "status": "active",
            "is_default": True,
        },
    )
    assert policy.status_code == 201

    create_intent = client.post(
        INTENTS_BASE,
        headers=org["org_headers"],
        json={
            "source_type": "recommendation_snapshot",
            "source_id": recommendation_snapshot["id"],
            "policy_id": policy.json()["policy_id"],
        },
    )
    assert create_intent.status_code == 201
    intent_id = create_intent.json()["intent_id"]

    row = db_session.get(GovernanceAutopilotExecutionIntent, uuid.UUID(intent_id))
    assert row is not None
    row.created_at = datetime.now(UTC) - timedelta(hours=52)
    row.updated_at = row.created_at
    db_session.add(row)
    db_session.commit()

    listed = client.get(INTENTS_BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    lrow = next(item for item in listed.json() if item["intent_id"] == intent_id)
    assert lrow["stale_intent"] is True
    assert lrow["intent_age_hours"] >= 24
    assert "pending_intent" in lrow["context_flags"]
    assert "stale_pending_intent" in lrow["context_flags"]

    detail = client.get(f"{INTENTS_BASE}/{intent_id}", headers=org["org_headers"])
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["stale_intent"] is True
    assert dbody["intent_age_hours"] >= 24
    assert "stale_pending_intent" in dbody["context_flags"]

    summary = client.get(f"{INTENTS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["pending_intents"] >= 1
    assert sbody["stale_pending_intents"] >= 1
    assert sbody["oldest_pending_intent_at"] is not None
    assert sbody["latest_intent_age_hours"] is not None
    assert "pending_execution_intents" in sbody["context_flags"]
    assert "stale_pending_intents_present" in sbody["context_flags"]
