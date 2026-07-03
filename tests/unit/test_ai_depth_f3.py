from __future__ import annotations

import uuid

from sqlalchemy import inspect, select

from app.models.ai_bias_assessment import AIBiasAssessment
from app.models.ai_system import AISystem
from app.models.audit_log import AuditLog
from app.models.issue import Issue
from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_system(client, headers: dict[str, str], owner_id: str, name: str, risk_tier: str = "limited") -> str:
    response = client.post(
        SYSTEMS_BASE,
        headers=headers,
        json={
            "name": name,
            "system_type": "model",
            "owner_id": owner_id,
            "deployment_status": "development",
            "risk_tier": risk_tier,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _create_and_publish_model_card(client, headers: dict[str, str], system_id: str, owner_id: str) -> None:
    create = client.post(
        f"{SYSTEMS_BASE}/{system_id}/model-card",
        headers=headers,
        json={
            "intended_purpose": "Risk scoring",
            "training_data_description": "curated training data",
            "known_limitations": ["limited coverage"],
            "performance_metrics": {"auc": 0.91},
            "approved_use_cases": ["fraud_detection"],
            "prohibited_use_cases": ["employment_decisions"],
            "contact_owner_id": owner_id,
        },
    )
    assert create.status_code == 201, create.text

    publish = client.post(f"{SYSTEMS_BASE}/{system_id}/model-cards/{create.json()['id']}/publish", headers=headers)
    assert publish.status_code == 200, publish.text


def test_ai_depth_schema_objects_exist(db_session):
    inspector = inspect(db_session.bind)
    tables = set(inspector.get_table_names())
    assert "ai_bias_assessments" in tables

    ai_system_cols = {c["name"] for c in inspector.get_columns("ai_systems")}
    assert "bias_assessment_status" in ai_system_cols
    assert "last_bias_assessment_at" in ai_system_cols
    assert "explainability_method" in ai_system_cols
    assert "human_oversight_level" in ai_system_cols
    assert "data_governance_score" in ai_system_cols
    assert "atlas_risk_score" in ai_system_cols


def test_bias_assessment_pass_fail_and_history(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ai-depth-bias")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Bias System")

    baseline_issues = db_session.execute(select(Issue)).scalars().all()
    assert len(baseline_issues) == 0

    passed = client.post(
        f"{SYSTEMS_BASE}/{system_id}/bias-assessments",
        headers=org["org_headers"],
        json={
            "assessment_method": "statistical_parity",
            "protected_attribute": "gender",
            "metric_name": "demographic_parity",
            "metric_value": 0.06,
            "threshold_value": 0.10,
            "lower_is_better": True,
            "remediation_notes": None,
        },
    )
    assert passed.status_code == 201, passed.text
    assert passed.json()["passed"] is True

    system = db_session.get(AISystem, uuid.UUID(system_id))
    assert system is not None
    assert system.bias_assessment_status == "completed"

    post_pass_issues = db_session.execute(select(Issue)).scalars().all()
    assert len(post_pass_issues) == 0

    failed = client.post(
        f"{SYSTEMS_BASE}/{system_id}/bias-assessments",
        headers=org["org_headers"],
        json={
            "assessment_method": "disparate_impact",
            "protected_attribute": "race",
            "metric_name": "disparate_impact",
            "metric_value": 0.58,
            "threshold_value": 0.80,
            "lower_is_better": False,
            "remediation_notes": "retrain with balanced sampling",
        },
    )
    assert failed.status_code == 201, failed.text
    assert failed.json()["passed"] is False

    system = db_session.get(AISystem, uuid.UUID(system_id))
    assert system is not None
    assert system.bias_assessment_status == "remediation_needed"

    issues = db_session.execute(select(Issue)).scalars().all()
    assert len(issues) == 1
    assert "Bias Detected in AI System" in issues[0].title

    history = client.get(f"{SYSTEMS_BASE}/{system_id}/bias-assessments", headers=org["org_headers"])
    assert history.status_code == 200
    history_rows = history.json()
    assert len(history_rows) == 2


def test_oversight_endpoint_and_high_risk_full_automation_issue(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ai-depth-over")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Oversight System", risk_tier="high")

    set_hil = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/oversight",
        headers=org["org_headers"],
        json={"oversight_level": "human_in_loop", "explainability_method": "shap"},
    )
    assert set_hil.status_code == 200, set_hil.text

    row = db_session.get(AISystem, uuid.UUID(system_id))
    assert row is not None
    assert row.human_oversight_level == "human_in_loop"
    assert row.explainability_method == "shap"

    before = db_session.execute(select(Issue)).scalars().all()
    assert len(before) == 0

    full_auto = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/oversight",
        headers=org["org_headers"],
        json={"oversight_level": "full_automation", "explainability_method": "none"},
    )
    assert full_auto.status_code == 200, full_auto.text

    after = db_session.execute(select(Issue)).scalars().all()
    assert len(after) == 1
    assert "High-Risk AI System Without Human Oversight" in after[0].title


def test_governance_score_and_scorecard_and_org_isolation(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ai-depth-a")
    org_b = bootstrap_org_user(client, email_prefix="ai-depth-b")

    low_system = _create_system(client, org_a["org_headers"], org_a["user_id"], "Low Gov")
    high_system = _create_system(client, org_a["org_headers"], org_a["user_id"], "High Gov")

    create_aibom = client.post(f"{SYSTEMS_BASE}/{high_system}/aibom", headers=org_a["org_headers"], json={})
    assert create_aibom.status_code == 201, create_aibom.text

    add_training_component = client.post(
        f"{SYSTEMS_BASE}/{high_system}/aibom/components",
        headers=org_a["org_headers"],
        json={"component_type": "training_data", "name": "core_training_set", "is_third_party": False},
    )
    assert add_training_component.status_code == 201, add_training_component.text

    _create_and_publish_model_card(client, org_a["org_headers"], high_system, org_a["user_id"])

    set_oversight = client.patch(
        f"{SYSTEMS_BASE}/{high_system}/oversight",
        headers=org_a["org_headers"],
        json={"oversight_level": "human_in_loop", "explainability_method": "lime"},
    )
    assert set_oversight.status_code == 200, set_oversight.text

    bias = client.post(
        f"{SYSTEMS_BASE}/{high_system}/bias-assessments",
        headers=org_a["org_headers"],
        json={
            "assessment_method": "fairlearn_manual",
            "protected_attribute": "age_group",
            "metric_name": "equalized_odds",
            "metric_value": 0.07,
            "threshold_value": 0.10,
            "lower_is_better": True,
        },
    )
    assert bias.status_code == 201, bias.text

    score_low = client.get(f"{SYSTEMS_BASE}/{low_system}/governance-score", headers=org_a["org_headers"])
    assert score_low.status_code == 200, score_low.text

    score_high = client.get(f"{SYSTEMS_BASE}/{high_system}/governance-score", headers=org_a["org_headers"])
    assert score_high.status_code == 200, score_high.text

    low_payload = score_low.json()
    high_payload = score_high.json()
    assert 0.0 <= low_payload["total_score"] <= 1.0
    assert 0.0 <= high_payload["total_score"] <= 1.0
    assert high_payload["grade"] in {"A", "B", "C", "D", "F"}
    assert high_payload["total_score"] > low_payload["total_score"]

    cached = db_session.get(AISystem, uuid.UUID(high_system))
    assert cached is not None
    assert cached.data_governance_score is not None

    scorecard = client.get("/api/v1/ai-governance/scorecard", headers=org_a["org_headers"])
    assert scorecard.status_code == 200
    scorecard_payload = scorecard.json()
    assert scorecard_payload["total_systems"] >= 2
    assert "avg_governance_score" in scorecard_payload["scorecard"]
    assert "bias_assessment_coverage" in scorecard_payload["scorecard"]

    cross_org = client.get(f"{SYSTEMS_BASE}/{high_system}/governance-score", headers=org_b["org_headers"])
    assert cross_org.status_code == 404


def test_ai_depth_audit_logging(client, db_session):
    org = bootstrap_org_user(client, email_prefix="ai-depth-audit")
    system_id = _create_system(client, org["org_headers"], org["user_id"], "Audit System")

    submit = client.post(
        f"{SYSTEMS_BASE}/{system_id}/bias-assessments",
        headers=org["org_headers"],
        json={
            "assessment_method": "statistical_parity",
            "protected_attribute": "gender",
            "metric_name": "demographic_parity",
            "metric_value": 0.03,
            "threshold_value": 0.05,
            "lower_is_better": True,
        },
    )
    assert submit.status_code == 201, submit.text

    patch = client.patch(
        f"{SYSTEMS_BASE}/{system_id}/oversight",
        headers=org["org_headers"],
        json={"oversight_level": "human_in_loop", "explainability_method": "counterfactual"},
    )
    assert patch.status_code == 200, patch.text

    logs = db_session.execute(select(AuditLog)).scalars().all()
    actions = {row.action for row in logs}
    assert "ai.bias_assessment_submitted" in actions
    assert "ai.oversight_level_updated" in actions

    assessments = db_session.execute(
        select(AIBiasAssessment).where(AIBiasAssessment.system_id == uuid.UUID(system_id))
    ).scalars().all()
    assert len(assessments) == 1
