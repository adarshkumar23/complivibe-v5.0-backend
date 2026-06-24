import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_autopilot_execution_intent import GovernanceAutopilotExecutionIntent
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_autopilot_policies_phase70 import (
    _create_draft_snapshot,
    _create_recommendation_snapshot,
    _first_candidate_action,
    _seed,
    POLICY_BASE,
)

CAP_ENDPOINT = "/api/v1/ai-governance/autopilot/capabilities"
PREVIEW_CANDIDATE = "/api/v1/ai-governance/autopilot/execution-intents/preview-candidate-action"
PREVIEW_RECO = "/api/v1/ai-governance/autopilot/execution-intents/preview-recommendation-snapshot"
PREVIEW_DRAFT = "/api/v1/ai-governance/autopilot/execution-intents/preview-copilot-draft-snapshot"
INTENTS_BASE = "/api/v1/ai-governance/autopilot/execution-intents"


def test_phase71_capability_matrix_and_deny_by_default(client):
    org = bootstrap_org_user(client, email_prefix="p71-cap")
    resp = client.get(CAP_ENDPOINT, headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["capabilities"], list)
    by_key = {item["capability_key"]: item for item in body["capabilities"]}
    assert by_key["refresh_signal_preview"]["default_allowed"] is True
    assert by_key["create_task"]["default_allowed"] is False
    assert by_key["create_task"]["allowed_in_phase_7_1"] is False
    assert by_key["external_notification"]["external_effects"] is True


def test_phase71_preview_candidate_action_read_only_no_audit_or_rows(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p71-prev-candidate")
    _, assessment, _ = _seed(client, org["org_headers"], name="P71-C1")
    candidate = _first_candidate_action(client, org["org_headers"], assessment_id=assessment["id"])

    before_rows = int(db_session.execute(select(func.count(GovernanceAutopilotExecutionIntent.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())

    resp = client.post(PREVIEW_CANDIDATE, headers=org["org_headers"], json={"candidate_action_json": candidate})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_type"] == "candidate_action"
    assert isinstance(body["source_hash"], str) and len(body["source_hash"]) == 64
    assert "capability_decisions_json" in body
    assert "blocked" in body

    after_rows = int(db_session.execute(select(func.count(GovernanceAutopilotExecutionIntent.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    assert after_rows == before_rows
    assert after_audit == before_audit
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews


def test_phase71_preview_recommendation_and_draft_read_only(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p71-prev-sources")
    _, assessment, _ = _seed(client, org["org_headers"], name="P71-Src")
    recommendation_snapshot = _create_recommendation_snapshot(client, org["org_headers"], assessment_id=assessment["id"])
    draft_snapshot = _create_draft_snapshot(client, org["org_headers"], assessment_id=assessment["id"])

    before_sig = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    before_payload = db_session.get(
        GovernanceRecommendationSnapshot,
        uuid.UUID(recommendation_snapshot["id"]),
    ).recommendation_payload_json

    reco = client.post(
        PREVIEW_RECO,
        headers=org["org_headers"],
        json={"recommendation_snapshot_id": recommendation_snapshot["id"]},
    )
    assert reco.status_code == 200
    reco_body = reco.json()
    assert reco_body["source_type"] == "recommendation_snapshot"
    assert reco_body["source_id"] == recommendation_snapshot["id"]
    assert isinstance(reco_body["capability_decisions_json"], dict)

    draft = client.post(
        PREVIEW_DRAFT,
        headers=org["org_headers"],
        json={"copilot_draft_snapshot_id": draft_snapshot["id"]},
    )
    assert draft.status_code == 200
    draft_body = draft.json()
    assert draft_body["source_type"] == "copilot_draft_snapshot"
    assert draft_body["source_id"] == draft_snapshot["id"]

    after_sig = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        ).scalars()
    }
    after_payload = db_session.get(
        GovernanceRecommendationSnapshot,
        uuid.UUID(recommendation_snapshot["id"]),
    ).recommendation_payload_json
    assert before_sig == after_sig
    assert before_payload == after_payload


def test_phase71_create_execution_intent_status_hash_and_archive(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p71-create")
    _, assessment, _ = _seed(client, org["org_headers"], name="P71-Creator")
    recommendation_snapshot = _create_recommendation_snapshot(client, org["org_headers"], assessment_id=assessment["id"])
    candidate = _first_candidate_action(client, org["org_headers"], assessment_id=assessment["id"])

    # Create permissive policy to produce approval_required (not blocked by mode).
    policy = client.post(
        POLICY_BASE,
        headers=org["org_headers"],
        json={
            "name": "p71-policy",
            "mode": "require_approval",
            "status": "active",
            "is_default": True,
        },
    )
    assert policy.status_code == 201
    policy_id = policy.json()["policy_id"]

    create_candidate_intent = client.post(
        INTENTS_BASE,
        headers=org["org_headers"],
        json={"source_type": "candidate_action", "candidate_action_json": candidate, "policy_id": policy_id},
    )
    assert create_candidate_intent.status_code == 201
    i1 = create_candidate_intent.json()
    assert i1["intent_status"] in {"blocked", "approval_required", "planned"}
    assert isinstance(i1["source_hash"], str) and len(i1["source_hash"]) == 64
    assert isinstance(i1["intent_sha256"], str) and len(i1["intent_sha256"]) == 64

    create_reco_intent = client.post(
        INTENTS_BASE,
        headers=org["org_headers"],
        json={
            "source_type": "recommendation_snapshot",
            "source_id": recommendation_snapshot["id"],
            "policy_id": policy_id,
        },
    )
    assert create_reco_intent.status_code == 201
    i2 = create_reco_intent.json()
    assert i2["source_type"] == "recommendation_snapshot"

    # deterministic hash for same input and same policy.
    create_candidate_intent_2 = client.post(
        INTENTS_BASE,
        headers=org["org_headers"],
        json={"source_type": "candidate_action", "candidate_action_json": candidate, "policy_id": policy_id},
    )
    assert create_candidate_intent_2.status_code == 201
    i3 = create_candidate_intent_2.json()
    assert i3["source_hash"] == i1["source_hash"]
    assert i3["intent_sha256"] == i1["intent_sha256"]

    listed = client.get(INTENTS_BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) >= 3

    detail = client.get(f"{INTENTS_BASE}/{i2['intent_id']}", headers=org["org_headers"])
    assert detail.status_code == 200
    assert detail.json()["intent_id"] == i2["intent_id"]

    before_count = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecutionIntent.id)).where(
                GovernanceAutopilotExecutionIntent.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    archive = client.post(
        f"{INTENTS_BASE}/{i2['intent_id']}/archive",
        headers=org["org_headers"],
        json={"reason": "archive test"},
    )
    assert archive.status_code == 200
    assert archive.json()["intent_status"] == "archived"
    after_count = int(
        db_session.execute(
            select(func.count(GovernanceAutopilotExecutionIntent.id)).where(
                GovernanceAutopilotExecutionIntent.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    assert after_count == before_count


def test_phase71_intent_summary_tenant_scope_audit_and_contracts(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p71-tenant-1")
    org2 = bootstrap_org_user(client, email_prefix="p71-tenant-2")
    _, assessment, _ = _seed(client, org1["org_headers"], name="P71-Tenant")
    recommendation_snapshot = _create_recommendation_snapshot(client, org1["org_headers"], assessment_id=assessment["id"])

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    create = client.post(
        INTENTS_BASE,
        headers=org1["org_headers"],
        json={"source_type": "recommendation_snapshot", "source_id": recommendation_snapshot["id"]},
    )
    assert create.status_code == 201
    intent_id = create.json()["intent_id"]
    after_create_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_create_audit > before_audit

    summary = client.get(f"{INTENTS_BASE}/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    sb = summary.json()
    assert sb["total_intents"] >= 1
    assert isinstance(sb["by_status"], dict)

    # read endpoints should not audit
    read_before = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    _ = client.get(INTENTS_BASE, headers=org1["org_headers"])
    _ = client.get(f"{INTENTS_BASE}/{intent_id}", headers=org1["org_headers"])
    _ = client.get(f"{INTENTS_BASE}/summary", headers=org1["org_headers"])
    read_after = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert read_after == read_before

    cross_detail = client.get(f"{INTENTS_BASE}/{intent_id}", headers=org2["org_headers"])
    assert cross_detail.status_code == 404

    contracts = client.get("/api/v1/ai-governance/contracts/phase7", headers=org1["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"] for g in contracts.json()["groups"]}
    assert "governance_autopilot_capabilities" in groups
    assert "governance_autopilot_execution_intents" in groups
