import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_recommendation_action_disposition import GovernanceRecommendationActionDisposition
from app.models.governance_recommendation_snapshot import GovernanceRecommendationSnapshot
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_recommendation_action_dispositions_phase69 import _create_snapshot, _seed

CATALOG_ENDPOINT = "/api/v1/ai-governance/copilot/draft-types"
GENERIC_ENDPOINT = "/api/v1/ai-governance/copilot/drafts/preview"


def _assert_draft_shape(body: dict, expected_type: str) -> None:
    assert body["draft_type"] == expected_type
    assert body["generation_mode"] == "deterministic_template"
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["executive_summary"], str) and body["executive_summary"]
    assert isinstance(body["key_findings"], list)
    assert isinstance(body["recommended_next_steps"], list)
    assert isinstance(body["open_questions"], list)
    assert len(body["key_findings"]) <= 5
    assert len(body["recommended_next_steps"]) <= 5
    assert len(body["open_questions"]) <= 5
    assert isinstance(body["source_signal_ids"], list)
    assert isinstance(body["source_action_identity_hashes"], list)
    assert isinstance(body["source_entities_json"], dict)
    assert "deterministic draft previews" in body["caveat"].lower()


def test_phase610_draft_type_catalog_and_contract_group(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p610-catalog")

    response = client.get(CATALOG_ENDPOINT, headers=org["org_headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["count"] >= 6
    keys = {item["draft_type"] for item in body["draft_types"]}
    assert {
        "ai_system_attention_brief",
        "risk_assessment_review_brief",
        "recommendation_snapshot_summary",
        "classification_review_brief",
        "executive_risk_summary",
        "action_plan_brief",
    }.issubset(keys)

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "governance_copilot_draft_previews" in groups


def test_phase610_generic_preview_validation_and_scope_ownership(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p610-preview-1")
    org2 = bootstrap_org_user(client, email_prefix="p610-preview-2")
    ai, assessment, _ = _seed(client, org1["org_headers"], name="P610-AI")

    before_snapshots = int(db_session.execute(select(func.count(GovernanceRecommendationSnapshot.id))).scalar_one())
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    ok = client.post(
        GENERIC_ENDPOINT,
        headers=org1["org_headers"],
        json={
            "draft_type": "ai_system_attention_brief",
            "scope_type": "ai_system",
            "scope_id": ai["id"],
            "include_resolved_signals": False,
        },
    )
    assert ok.status_code == 200
    _assert_draft_shape(ok.json(), "ai_system_attention_brief")

    invalid = client.post(
        GENERIC_ENDPOINT,
        headers=org1["org_headers"],
        json={"draft_type": "not_a_type", "scope_type": "organization"},
    )
    assert invalid.status_code in (400, 422)

    cross = client.post(
        GENERIC_ENDPOINT,
        headers=org2["org_headers"],
        json={
            "draft_type": "risk_assessment_review_brief",
            "scope_type": "risk_assessment",
            "scope_id": assessment["id"],
        },
    )
    assert cross.status_code == 404

    after_snapshots = int(db_session.execute(select(func.count(GovernanceRecommendationSnapshot.id))).scalar_one())
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert after_snapshots == before_snapshots
    assert after_audit == before_audit


def test_phase610_ai_system_and_assessment_briefs_read_only_no_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p610-briefs")
    ai, assessment, _ = _seed(client, org["org_headers"], name="P610-AI-Briefs")

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_signal_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        )
        .scalars()
        .all()
    }

    ai_brief = client.get(
        f"/api/v1/ai-governance/ai-systems/{ai['id']}/copilot-brief",
        headers=org["org_headers"],
    )
    assert ai_brief.status_code == 200
    _assert_draft_shape(ai_brief.json(), "ai_system_attention_brief")

    assessment_brief = client.get(
        f"/api/v1/ai-governance/ai-risk/assessments/{assessment['id']}/copilot-brief",
        headers=org["org_headers"],
    )
    assert assessment_brief.status_code == 200
    _assert_draft_shape(assessment_brief.json(), "risk_assessment_review_brief")

    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    after_signal_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]))
        )
        .scalars()
        .all()
    }
    assert after_audit == before_audit
    assert after_tasks == before_tasks
    assert after_reviews == before_reviews
    assert after_signal_statuses == before_signal_statuses


def test_phase610_recommendation_snapshot_copilot_summary_with_dispositions(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p610-snapshot")
    _, assessment, _ = _seed(client, org["org_headers"], name="P610-AI-Snapshot")
    snapshot = _create_snapshot(client, org["org_headers"], scope_type="risk_assessment", scope_id=assessment["id"])

    actions = client.get(
        f"/api/v1/ai-governance/recommendations/snapshots/{snapshot['id']}/actions",
        headers=org["org_headers"],
    )
    assert actions.status_code == 200
    action = actions.json()["actions"][0]

    ack = client.post(
        f"/api/v1/ai-governance/recommendations/snapshots/{snapshot['id']}/actions/{action['action_identity_hash']}/acknowledge",
        headers=org["org_headers"],
        json={"note": "seen"},
    )
    assert ack.status_code == 200

    before_payload = db_session.get(GovernanceRecommendationSnapshot, uuid.UUID(snapshot["id"])).recommendation_payload_json
    before_disposition_count = int(
        db_session.execute(
            select(func.count(GovernanceRecommendationActionDisposition.id)).where(
                GovernanceRecommendationActionDisposition.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    summary = client.get(
        f"/api/v1/ai-governance/recommendations/snapshots/{snapshot['id']}/copilot-summary",
        headers=org["org_headers"],
        params={"include_dispositions": True},
    )
    assert summary.status_code == 200
    body = summary.json()
    _assert_draft_shape(body, "recommendation_snapshot_summary")
    assert body["source_recommendation_snapshot_id"] == snapshot["id"]
    assert body["source_action_identity_hashes"]

    after_payload = db_session.get(GovernanceRecommendationSnapshot, uuid.UUID(snapshot["id"])).recommendation_payload_json
    after_disposition_count = int(
        db_session.execute(
            select(func.count(GovernanceRecommendationActionDisposition.id)).where(
                GovernanceRecommendationActionDisposition.organization_id == uuid.UUID(org["organization_id"])
            )
        ).scalar_one()
    )
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())

    assert after_payload == before_payload
    assert after_disposition_count == before_disposition_count
    assert after_audit == before_audit


def test_phase610_executive_summary_and_generic_action_plan(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p610-exec")
    ai, _, _ = _seed(client, org["org_headers"], name="P610-AI-Exec")

    executive = client.get(
        "/api/v1/ai-governance/copilot/executive-risk-summary",
        headers=org["org_headers"],
    )
    assert executive.status_code == 200
    _assert_draft_shape(executive.json(), "executive_risk_summary")

    action_plan = client.post(
        GENERIC_ENDPOINT,
        headers=org["org_headers"],
        json={
            "draft_type": "action_plan_brief",
            "scope_type": "ai_system",
            "scope_id": ai["id"],
        },
    )
    assert action_plan.status_code == 200
    _assert_draft_shape(action_plan.json(), "action_plan_brief")
