import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.ai_system_governance_review import AISystemGovernanceReview
from app.models.audit_log import AuditLog
from app.models.governance_signal import GovernanceSignal
from app.models.task import Task
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_risk_classification_phase64 import (
    CLASSIFICATION_BASE,
    _create_ai_system,
    _create_assessment,
    _create_taxonomy,
)
from tests.unit.test_ai_system_risk_classification_review_signals_phase65 import _create_classification


def _create_signal_flow(client, headers: dict[str, str], classification_id: str) -> None:
    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/submit-for-review",
        headers=headers,
        json={},
    )
    assert submit.status_code == 200
    changes = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/request-changes",
        headers=headers,
        json={"change_request_note": "needs updates"},
    )
    assert changes.status_code == 200


def test_phase67_action_template_catalog_and_contract_group(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p67-catalog")
    catalog = client.get("/api/v1/ai-governance/actions/templates", headers=org["org_headers"])
    assert catalog.status_code == 200
    body = catalog.json()
    assert body["count"] >= 7
    assert any(item["action_key"] == "create_classification_record" for item in body["templates"])
    assert all(item["automation_allowed"] is False for item in body["templates"])

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "governance_candidate_actions" in groups


def test_phase67_candidate_actions_generated_grouped_sorted_and_filtered(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p67-candidates")
    ai = _create_ai_system(client, org["org_headers"], name="P67-AI")
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="high")
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"], confidence_level="low")
    _create_signal_flow(client, org["org_headers"], classification["id"])

    # Add a second mapped signal with same target/action so grouping is exercised.
    db_session.add(
        GovernanceSignal(
            organization_id=uuid.UUID(org["organization_id"]),
            domain="ai_risk",
            entity_type="risk_classification",
            entity_id=uuid.UUID(classification["id"]),
            related_ai_system_id=uuid.UUID(ai["id"]),
            related_risk_assessment_id=uuid.UUID(assessment["id"]),
            signal_type="classification_needs_review",
            reason_code="classification_needs_review",
            severity="info",
            status="open",
            title="Classification needs review duplicate",
            message="Manual duplicate for grouping test",
            source_json={"rule": "manual_test"},
            created_by_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    # Add one unmapped open signal that should not generate candidate actions.
    db_session.add(
        GovernanceSignal(
            organization_id=uuid.UUID(org["organization_id"]),
            domain="ai_risk",
            entity_type="risk_assessment",
            entity_id=uuid.UUID(assessment["id"]),
            related_ai_system_id=uuid.UUID(ai["id"]),
            related_risk_assessment_id=uuid.UUID(assessment["id"]),
            signal_type="unmapped_signal_type",
            reason_code="unmapped_reason_code",
            severity="critical",
            status="open",
            title="Unmapped signal",
            message="Should not map to action",
            source_json={"rule": "manual_unmapped"},
            created_by_system=True,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    db_session.commit()

    response = client.get("/api/v1/ai-governance/actions/candidates", headers=org["org_headers"])
    assert response.status_code == 200
    rows = response.json()
    assert rows
    assert all("unmapped_reason_code" not in row["source_reason_codes"] for row in rows)
    assert all(row["automation_allowed"] is False for row in rows)
    assert all(row["human_approval_required"] is True for row in rows)

    grouped = [row for row in rows if row["action_key"] == "review_classification"]
    assert grouped
    assert len(grouped[0]["source_signal_ids"]) >= 2
    assert float(grouped[0]["priority_score"]) >= 40.0

    scores = [float(row["priority_score"]) for row in rows]
    assert scores == sorted(scores, reverse=True)

    filtered_ai = client.get(
        f"/api/v1/ai-governance/actions/candidates?related_ai_system_id={ai['id']}",
        headers=org["org_headers"],
    )
    assert filtered_ai.status_code == 200
    assert all(item["related_ai_system_id"] == ai["id"] for item in filtered_ai.json())

    filtered_assessment = client.get(
        f"/api/v1/ai-governance/actions/candidates?related_risk_assessment_id={assessment['id']}",
        headers=org["org_headers"],
    )
    assert filtered_assessment.status_code == 200
    assert all(item["related_risk_assessment_id"] == assessment["id"] for item in filtered_assessment.json())


def test_phase67_candidate_endpoints_are_read_only_and_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p67-readonly")
    ai = _create_ai_system(client, org["org_headers"], name="P67-AI-Read")
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"])
    _create_signal_flow(client, org["org_headers"], classification["id"])

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    before_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    before_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    before_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(
                GovernanceSignal.organization_id == uuid.UUID(org["organization_id"])
            )
        )
        .scalars()
        .all()
    }

    candidates = client.get("/api/v1/ai-governance/actions/candidates", headers=org["org_headers"])
    assert candidates.status_code == 200
    summary = client.get("/api/v1/ai-governance/actions/candidate-summary", headers=org["org_headers"])
    assert summary.status_code == 200

    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert before_audit == after_audit
    after_tasks = int(db_session.execute(select(func.count(Task.id))).scalar_one())
    after_reviews = int(db_session.execute(select(func.count(AISystemGovernanceReview.id))).scalar_one())
    assert before_tasks == after_tasks
    assert before_reviews == after_reviews

    after_statuses = {
        row.id: row.status
        for row in db_session.execute(
            select(GovernanceSignal).where(
                GovernanceSignal.organization_id == uuid.UUID(org["organization_id"])
            )
        )
        .scalars()
        .all()
    }
    assert before_statuses == after_statuses


def test_phase67_ai_system_and_assessment_candidate_actions_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p67-view-1")
    org2 = bootstrap_org_user(client, email_prefix="p67-view-2")
    ai = _create_ai_system(client, org1["org_headers"], name="P67-AI-View")
    assessment = _create_assessment(client, org1["org_headers"], ai["id"])
    _create_taxonomy(client, org1["org_headers"], is_default=True)
    classification = _create_classification(client, org1["org_headers"], assessment["id"])
    _create_signal_flow(client, org1["org_headers"], classification["id"])

    ai_view = client.get(
        f"/api/v1/ai-governance/ai-systems/{ai['id']}/candidate-actions",
        headers=org1["org_headers"],
    )
    assert ai_view.status_code == 200
    ai_body = ai_view.json()
    assert ai_body["ai_system_id"] == ai["id"]
    assert ai_body["candidate_action_count"] >= 1
    assert ai_body["actions"]

    assessment_view = client.get(
        f"/api/v1/ai-governance/ai-risk/assessments/{assessment['id']}/candidate-actions",
        headers=org1["org_headers"],
    )
    assert assessment_view.status_code == 200
    assessment_body = assessment_view.json()
    assert assessment_body["assessment_id"] == assessment["id"]
    assert assessment_body["candidate_action_count"] >= 1

    cross_ai = client.get(
        f"/api/v1/ai-governance/ai-systems/{ai['id']}/candidate-actions",
        headers=org2["org_headers"],
    )
    assert cross_ai.status_code == 404
    cross_assessment = client.get(
        f"/api/v1/ai-governance/ai-risk/assessments/{assessment['id']}/candidate-actions",
        headers=org2["org_headers"],
    )
    assert cross_assessment.status_code == 404


def test_phase67_candidate_summary_and_explain_endpoint(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p67-summary")
    ai = _create_ai_system(client, org["org_headers"], name="P67-AI-Summary")
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"])
    _create_signal_flow(client, org["org_headers"], classification["id"])

    summary = client.get("/api/v1/ai-governance/actions/candidate-summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_candidate_actions"] >= 1
    assert isinstance(body["by_action_type"], dict)
    assert isinstance(body["by_priority_band"], dict)
    assert isinstance(body["top_action_keys"], list)
    assert isinstance(body["top_ai_systems_by_action_count"], list)

    explain = client.get(
        "/api/v1/ai-governance/actions/candidates/explain",
        headers=org["org_headers"],
        params={"action_key": "review_classification", "related_ai_system_id": ai["id"]},
    )
    assert explain.status_code == 200
    ex = explain.json()
    assert ex["action_key"] == "review_classification"
    assert ex["rationale_json"]["algorithm"] == "governance_candidate_actions_v1"

    missing = client.get(
        "/api/v1/ai-governance/actions/candidates/explain",
        headers=org["org_headers"],
        params={"action_key": "does_not_exist"},
    )
    assert missing.status_code == 404
