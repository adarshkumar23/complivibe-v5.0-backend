import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_policy import GovernanceAutopilotPolicy
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_candidate_actions_phase67 import _create_signal_flow
from tests.unit.test_ai_system_risk_classification_phase64 import (
    _create_ai_system,
    _create_assessment,
    _create_taxonomy,
)
from tests.unit.test_ai_system_risk_classification_review_signals_phase65 import _create_classification

POLICY_BASE = "/api/v1/ai-governance/autopilot/policies"
EVAL_CANDIDATE_ENDPOINT = "/api/v1/ai-governance/autopilot/evaluate-candidate-action"
EVAL_RECOMMENDATION_ENDPOINT = "/api/v1/ai-governance/autopilot/evaluate-recommendation-snapshot"
EVAL_DRAFT_ENDPOINT = "/api/v1/ai-governance/autopilot/evaluate-copilot-draft-snapshot"


def _seed(client, headers: dict[str, str], *, name: str = "P70-AI") -> tuple[dict, dict, dict]:
    ai = _create_ai_system(client, headers, name=name)
    assessment = _create_assessment(client, headers, ai["id"], risk_level="high")
    _create_taxonomy(client, headers, is_default=True)
    classification = _create_classification(client, headers, assessment["id"], confidence_level="low")
    _create_signal_flow(client, headers, classification["id"])
    return ai, assessment, classification


def _first_candidate_action(client, headers: dict[str, str], *, assessment_id: str) -> dict:
    resp = client.get(
        f"/api/v1/ai-governance/ai-risk/assessments/{assessment_id}/candidate-actions",
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["actions"]
    return body["actions"][0]


def _create_recommendation_snapshot(client, headers: dict[str, str], *, assessment_id: str) -> dict:
    resp = client.post(
        "/api/v1/ai-governance/recommendations/snapshots",
        headers=headers,
        json={"scope_type": "risk_assessment", "scope_id": assessment_id},
    )
    assert resp.status_code == 201
    return resp.json()


def _create_draft_snapshot(client, headers: dict[str, str], *, assessment_id: str) -> dict:
    resp = client.post(
        "/api/v1/ai-governance/copilot/draft-snapshots",
        headers=headers,
        json={
            "draft_type": "risk_assessment_review_brief",
            "scope_type": "risk_assessment",
            "scope_id": assessment_id,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_phase70_autopilot_policy_crud_default_resolved_and_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p70-crud")
    headers = org["org_headers"]

    create = client.post(
        POLICY_BASE,
        headers=headers,
        json={"name": "safe-policy", "mode": "suggest_only", "is_default": True},
    )
    assert create.status_code == 201
    created = create.json()
    assert created["name"] == "safe-policy"
    assert created["is_default"] is True
    assert created["external_effects_allowed"] is False

    listed = client.get(POLICY_BASE, headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    detail = client.get(f"{POLICY_BASE}/{created['policy_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["policy_id"] == created["policy_id"]

    update = client.patch(
        f"{POLICY_BASE}/{created['policy_id']}",
        headers=headers,
        json={"mode": "require_approval"},
    )
    assert update.status_code == 200
    assert update.json()["mode"] == "require_approval"

    create_two = client.post(
        POLICY_BASE,
        headers=headers,
        json={"name": "policy-two", "mode": "observe_only", "is_default": False},
    )
    assert create_two.status_code == 201
    second = create_two.json()

    set_default = client.post(f"{POLICY_BASE}/{second['policy_id']}/set-default", headers=headers)
    assert set_default.status_code == 200
    assert set_default.json()["is_default"] is True

    resolved = client.get(f"{POLICY_BASE}/resolved", headers=headers)
    assert resolved.status_code == 200
    assert resolved.json()["policy_id"] == second["policy_id"]
    assert resolved.json()["resolved_source"] == "persisted_default"

    archive = client.post(f"{POLICY_BASE}/{second['policy_id']}/archive", headers=headers, json={"reason": "retired"})
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    resolved_fallback = client.get(f"{POLICY_BASE}/resolved", headers=headers)
    assert resolved_fallback.status_code == 200
    assert resolved_fallback.json()["policy_id"] is None
    assert resolved_fallback.json()["mode"] == "suggest_only"
    assert resolved_fallback.json()["resolved_source"] == "safe_fallback_default"

    summary = client.get("/api/v1/ai-governance/autopilot/summary", headers=headers)
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_policies"] >= 2
    assert "resolved_mode" in sb
    assert sb["resolved_source"] == "safe_fallback_default"
    assert sb["pending_execution_intents"] >= 0
    assert sb["pending_approval_requests"] >= 0
    assert sb["open_critical_signals"] >= 0
    assert sb["stale_default_policy"] is False
    assert "safe_fallback_policy" in sb["context_flags"]
    assert sb["policy_data_age_days"] is None or sb["policy_data_age_days"] >= 0

    # no hard delete
    count_rows = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotPolicy.id)).where(
                GovernanceAutopilotPolicy.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    assert count_rows >= 2


def test_phase70_autopilot_policy_validation_and_tenant_scope(client):
    org1 = bootstrap_org_user(client, email_prefix="p70-val-1")
    org2 = bootstrap_org_user(client, email_prefix="p70-val-2")

    invalid_mode = client.post(POLICY_BASE, headers=org1["org_headers"], json={"name": "bad", "mode": "nope"})
    assert invalid_mode.status_code == 422

    invalid_status = client.post(POLICY_BASE, headers=org1["org_headers"], json={"name": "bad2", "status": "zzz"})
    assert invalid_status.status_code == 422

    created = client.post(POLICY_BASE, headers=org1["org_headers"], json={"name": "tenant-policy", "mode": "suggest_only"})
    assert created.status_code == 201
    policy_id = created.json()["policy_id"]

    cross_detail = client.get(f"{POLICY_BASE}/{policy_id}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    cross_update = client.patch(f"{POLICY_BASE}/{policy_id}", headers=org2["org_headers"], json={"mode": "disabled"})
    assert cross_update.status_code == 404


def test_phase70_candidate_evaluation_blocks_and_requires_approval(client):
    org = bootstrap_org_user(client, email_prefix="p70-eval-candidate")
    headers = org["org_headers"]
    _, assessment, _ = _seed(client, headers, name="P70-Candidate")
    candidate = _first_candidate_action(client, headers, assessment_id=assessment["id"])

    # safe fallback: high/urgent should require approval
    candidate_high = dict(candidate)
    candidate_high["priority_band"] = "high"
    candidate_high["risk_tier"] = "high"
    eval_fallback = client.post(
        EVAL_CANDIDATE_ENDPOINT,
        headers=headers,
        json={"candidate_action_json": candidate_high},
    )
    assert eval_fallback.status_code == 200
    fallback_body = eval_fallback.json()
    assert fallback_body["requires_human_approval"] is True
    assert "human_approval_required" in fallback_body["context_flags"]
    assert "safe_fallback_policy" in fallback_body["context_flags"]
    if fallback_body["risk_tier"] == "high":
        assert "high_risk_action" in fallback_body["context_flags"]
    assert fallback_body["policy_data_age_days"] is None or fallback_body["policy_data_age_days"] >= 0

    policy = client.post(
        POLICY_BASE,
        headers=headers,
        json={
            "name": "block-update",
            "mode": "suggest_only",
            "blocked_action_types_json": [candidate["action_type"]],
            "is_default": False,
        },
    )
    assert policy.status_code == 201
    policy_id = policy.json()["policy_id"]

    eval_blocked = client.post(
        EVAL_CANDIDATE_ENDPOINT,
        headers=headers,
        json={"candidate_action_json": candidate, "policy_id": policy_id},
    )
    assert eval_blocked.status_code == 200
    blocked_body = eval_blocked.json()
    assert blocked_body["allowed_by_policy"] is False
    assert "action_type_blocked" in blocked_body["blocked_reasons"]
    assert "policy_blocked" in blocked_body["context_flags"]


def test_phase70_recommendation_and_copilot_evaluation_and_no_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p70-eval-snap")
    headers = org["org_headers"]
    _, assessment, _ = _seed(client, headers, name="P70-Snap")

    recommendation_snapshot = _create_recommendation_snapshot(client, headers, assessment_id=assessment["id"])
    draft_snapshot = _create_draft_snapshot(client, headers, assessment_id=assessment["id"])
    candidate = _first_candidate_action(client, headers, assessment_id=assessment["id"])

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_payload = db_session.get(
        GovernanceRecommendationSnapshot,
        uuid.UUID(recommendation_snapshot["id"]),
    ).recommendation_payload_json

    eval_reco = client.post(
        EVAL_RECOMMENDATION_ENDPOINT,
        headers=headers,
        json={"recommendation_snapshot_id": recommendation_snapshot["id"]},
    )
    assert eval_reco.status_code == 200
    reco_body = eval_reco.json()
    assert reco_body["snapshot_id"] == recommendation_snapshot["id"]
    assert reco_body["total_actions"] >= 1
    assert isinstance(reco_body["decisions"], list)
    assert 0 <= reco_body["blocked_ratio"] <= 1
    assert reco_body["highest_risk_tier"] in {"low", "medium", "high"}
    assert isinstance(reco_body["context_flags"], list)

    eval_draft = client.post(
        EVAL_DRAFT_ENDPOINT,
        headers=headers,
        json={"copilot_draft_snapshot_id": draft_snapshot["id"]},
    )
    assert eval_draft.status_code == 200
    draft_eval_body = eval_draft.json()
    assert draft_eval_body["snapshot_id"] == draft_snapshot["id"]
    assert "policy_explanation_json" in draft_eval_body
    assert "context_flags" in draft_eval_body
    assert draft_eval_body["policy_data_age_days"] is None or draft_eval_body["policy_data_age_days"] >= 0

    eval_candidate = client.post(
        EVAL_CANDIDATE_ENDPOINT,
        headers=headers,
        json={"candidate_action_json": candidate},
    )
    assert eval_candidate.status_code == 200

    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_signals = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    after_payload = db_session.get(
        GovernanceRecommendationSnapshot,
        uuid.UUID(recommendation_snapshot["id"]),
    ).recommendation_payload_json

    assert after_audit == before_audit
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews
    assert after_signals == before_signals
    assert after_payload == before_payload


def test_phase70_stale_policy_context_flags_for_candidate_and_summary(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p70-stale")
    headers = org["org_headers"]
    _, assessment, _ = _seed(client, headers, name="P70-Stale")
    candidate = _first_candidate_action(client, headers, assessment_id=assessment["id"])

    create = client.post(
        POLICY_BASE,
        headers=headers,
        json={
            "name": "stale-default",
            "mode": "suggest_only",
            "is_default": True,
        },
    )
    assert create.status_code == 201
    policy_id = uuid.UUID(create.json()["policy_id"])
    policy_row = db_session.get(GovernanceAutopilotPolicy, policy_id)
    assert policy_row is not None
    policy_row.updated_at = policy_row.updated_at - timedelta(days=120)
    db_session.add(policy_row)
    db_session.commit()

    eval_candidate = client.post(
        EVAL_CANDIDATE_ENDPOINT,
        headers=headers,
        json={"candidate_action_json": candidate, "policy_id": str(policy_id)},
    )
    assert eval_candidate.status_code == 200
    candidate_body = eval_candidate.json()
    assert candidate_body["policy_data_age_days"] >= 120
    assert "policy_definition_stale_90d" in candidate_body["context_flags"]

    summary = client.get("/api/v1/ai-governance/autopilot/summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["default_policy_id"] == str(policy_id)
    assert summary_body["policy_data_age_days"] >= 120
    assert summary_body["stale_default_policy"] is True
    assert "default_policy_stale_90d" in summary_body["context_flags"]


def test_phase70_policy_writes_audit_and_evaluation_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p70-audit")
    headers = org["org_headers"]
    _, assessment, _ = _seed(client, headers, name="P70-Audit")
    candidate = _first_candidate_action(client, headers, assessment_id=assessment["id"])

    before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    created = client.post(POLICY_BASE, headers=headers, json={"name": "audit-policy", "mode": "suggest_only"})
    assert created.status_code == 201
    pid = created.json()["policy_id"]
    updated = client.patch(f"{POLICY_BASE}/{pid}", headers=headers, json={"mode": "require_approval"})
    assert updated.status_code == 200
    defaulted = client.post(f"{POLICY_BASE}/{pid}/set-default", headers=headers)
    assert defaulted.status_code == 200
    archived = client.post(f"{POLICY_BASE}/{pid}/archive", headers=headers, json={"reason": "done"})
    assert archived.status_code == 200
    after_write = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_write >= before + 4

    eval_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.post(EVAL_CANDIDATE_ENDPOINT, headers=headers, json={"candidate_action_json": candidate})
    _ = client.get(f"{POLICY_BASE}", headers=headers)
    _ = client.get(f"{POLICY_BASE}/resolved", headers=headers)
    _ = client.get("/api/v1/ai-governance/autopilot/summary", headers=headers)
    eval_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert eval_after == eval_before

    actions = {
        row[0]
        for row in db_session.execute(
            select(AuditLog.action).where(AuditLog.organization_id == uuid.UUID(org["organization_id"]))
        ).all()
    }
    assert "governance_autopilot_policy.created" in actions
    assert "governance_autopilot_policy.updated" in actions
    assert "governance_autopilot_policy.default_set" in actions
    assert "governance_autopilot_policy.archived" in actions


def test_phase70_phase7_contract_endpoint_and_groups(client):
    org = bootstrap_org_user(client, email_prefix="p70-contract")
    headers = org["org_headers"]
    resp = client.get("/api/v1/ai-governance/contracts/phase7", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "phase7"
    groups = {g["group_key"] for g in body["groups"]}
    assert "governance_autopilot_policies" in groups
    assert "governance_autopilot_policy_evaluations" in groups
