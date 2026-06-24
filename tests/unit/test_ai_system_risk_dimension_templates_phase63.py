from sqlalchemy import func, select

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_dimension_template import AISystemRiskDimensionTemplate
from app.models.ai_system_risk_scoring_profile import AISystemRiskScoringProfile
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

ASSESSMENTS_BASE = "/api/v1/ai-governance/ai-risk/assessments"
SCORING_BASE = "/api/v1/ai-governance/ai-risk/scoring-profiles"
DIMENSIONS_BASE = "/api/v1/ai-governance/ai-risk/dimension-templates"


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Risk-Dimension AI") -> dict:
    response = client.post("/api/v1/ai-systems", headers=headers, json={"name": name, "system_type": "agent"})
    assert response.status_code == 201
    return response.json()


def _create_assessment(client, headers: dict[str, str], ai_system_id: str, **overrides) -> dict:
    payload = {
        "ai_system_id": ai_system_id,
        "title": "Risk Assessment",
        "assessment_type": "initial",
        "risk_level": "medium",
        "likelihood": "high",
        "impact": "medium",
    }
    payload.update(overrides)
    response = client.post(ASSESSMENTS_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_scoring_profile(client, headers: dict[str, str], **overrides) -> dict:
    payload = {"name": "Default Score Profile"}
    payload.update(overrides)
    response = client.post(SCORING_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_dimension_template(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "name": "Default Dimensions",
        "dimension_weights_json": {
            "safety": 1.5,
            "privacy": 1.2,
            "security": 1.2,
            "fairness": 1.0,
            "transparency": 0.8,
            "human_oversight": 1.0,
            "reliability": 1.1,
            "data_quality": 1.0,
            "legal_regulatory": 1.3,
            "third_party": 0.9,
            "operational": 0.8,
            "reputational": 0.7,
        },
        "dimension_thresholds_json": [
            {"min_score": 1.0, "max_score": 1.75, "risk_level": "low"},
            {"min_score": 1.76, "max_score": 2.5, "risk_level": "medium"},
            {"min_score": 2.51, "max_score": 3.25, "risk_level": "high"},
            {"min_score": 3.26, "max_score": 4.0, "risk_level": "critical"},
        ],
        "is_default": False,
    }
    payload.update(overrides)
    response = client.post(DIMENSIONS_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase63_dimension_template_crud_validation_default_and_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p63-dim-org1")
    org2 = bootstrap_org_user(client, email_prefix="p63-dim-org2")

    d1 = _create_dimension_template(client, org1["org_headers"], is_default=True)
    assert d1["is_default"] is True
    assert d1["status"] == "active"

    bad_dimension = client.post(
        DIMENSIONS_BASE,
        headers=org1["org_headers"],
        json={
            "name": "Bad key",
            "dimension_weights_json": {"unknown_key": 1.0},
            "dimension_thresholds_json": [{"min_score": 1, "max_score": 4, "risk_level": "high"}],
        },
    )
    assert bad_dimension.status_code == 400

    bad_weight = client.post(
        DIMENSIONS_BASE,
        headers=org1["org_headers"],
        json={
            "name": "Bad weight",
            "dimension_weights_json": {
                "safety": -1,
                "privacy": 1,
                "security": 1,
                "fairness": 1,
                "transparency": 1,
                "human_oversight": 1,
                "reliability": 1,
                "data_quality": 1,
                "legal_regulatory": 1,
                "third_party": 1,
                "operational": 1,
                "reputational": 1,
            },
            "dimension_thresholds_json": [{"min_score": 1, "max_score": 4, "risk_level": "high"}],
        },
    )
    assert bad_weight.status_code == 400

    bad_thresholds = client.post(
        DIMENSIONS_BASE,
        headers=org1["org_headers"],
        json={
            "name": "Overlap",
            "dimension_weights_json": d1["dimension_weights_json"],
            "dimension_thresholds_json": [
                {"min_score": 1, "max_score": 2.0, "risk_level": "low"},
                {"min_score": 2.0, "max_score": 3.0, "risk_level": "medium"},
            ],
        },
    )
    assert bad_thresholds.status_code == 400

    d2 = _create_dimension_template(client, org1["org_headers"], name="D2", is_default=False)
    set_default = client.post(f"{DIMENSIONS_BASE}/{d2['id']}/set-default", headers=org1["org_headers"], json={})
    assert set_default.status_code == 200
    assert set_default.json()["is_default"] is True
    d1_refetch = client.get(f"{DIMENSIONS_BASE}/{d1['id']}", headers=org1["org_headers"])
    assert d1_refetch.status_code == 200
    assert d1_refetch.json()["is_default"] is False

    cross_org_get = client.get(f"{DIMENSIONS_BASE}/{d1['id']}", headers=org2["org_headers"])
    assert cross_org_get.status_code == 404

    archived = client.post(
        f"{DIMENSIONS_BASE}/{d1['id']}/archive",
        headers=org1["org_headers"],
        json={"reason": "retired"},
    )
    assert archived.status_code == 200
    cannot_update_archived = client.patch(
        f"{DIMENSIONS_BASE}/{d1['id']}",
        headers=org1["org_headers"],
        json={"description": "nope"},
    )
    assert cannot_update_archived.status_code == 400


def test_phase63_preview_dimension_read_only_and_apply_template_behavior(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p63-preview")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="high")
    template = _create_dimension_template(client, org["org_headers"], is_default=True)

    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    preview = client.post(
        f"{DIMENSIONS_BASE}/{template['id']}/preview-score",
        headers=org["org_headers"],
        json={
            "dimension_inputs_json": {
                "safety": {"level": "high", "notes": "manual"},
                "privacy": {"level": "medium"},
                "security": {"level": "low"},
            }
        },
    )
    assert preview.status_code == 200
    pbody = preview.json()
    assert pbody["dimension_weighted_score"] is not None
    assert pbody["calculated_dimension_risk_level"] in {"low", "medium", "high", "critical"}
    assert pbody["dimension_score_json"]["algorithm"] == "manual_dimension_weighted_v1"
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert before_audit == after_audit

    applied = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-dimension-template",
        headers=org["org_headers"],
        json={
            "dimension_template_id": template["id"],
            "dimension_inputs_json": {
                "safety": {"level": "critical"},
                "privacy": {"level": "high"},
                "security": {"level": "high"},
            },
        },
    )
    assert applied.status_code == 200
    abody = applied.json()
    assert abody["dimension_template_id"] == template["id"]
    assert abody["dimension_template_snapshot_json"]["name"] == template["name"]
    assert abody["dimension_score_json"]["algorithm"] == "manual_dimension_weighted_v1"
    assert abody["risk_level"] == "high"  # manual stays unchanged

    applied_default = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-dimension-template",
        headers=org["org_headers"],
        json={
            "dimension_inputs_json": {
                "safety": {"level": "medium"},
                "privacy": {"level": "medium"},
            }
        },
    )
    assert applied_default.status_code == 200
    assert applied_default.json()["dimension_template_id"] == template["id"]

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "ai_system_risk_assessment.dimension_template_applied" in actions


def test_phase63_residual_preview_apply_scoring_profile_rules_and_unknown_values(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p63-residual")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"], likelihood="high", impact="high", risk_level="critical")
    default_profile = _create_scoring_profile(client, org["org_headers"], is_default=True)

    preview = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/preview-residual-risk",
        headers=org["org_headers"],
        json={"residual_likelihood": "medium", "residual_impact": "high"},
    )
    assert preview.status_code == 200
    pr_body = preview.json()
    assert pr_body["residual_risk_score"] == 6
    assert pr_body["calculated_residual_risk_level"] == "medium"

    applied = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-residual-risk",
        headers=org["org_headers"],
        json={"residual_likelihood": "medium", "residual_impact": "high"},
    )
    assert applied.status_code == 200
    ar_body = applied.json()
    assert ar_body["residual_likelihood"] == "medium"
    assert ar_body["residual_impact"] == "high"
    assert ar_body["residual_risk_score"] == 6
    assert ar_body["calculated_residual_risk_level"] == "medium"
    assert ar_body["residual_score_explanation_json"]["profile"]["profile_id"] == default_profile["id"]
    assert ar_body["risk_level"] == "critical"

    unknown_preview = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/preview-residual-risk",
        headers=org["org_headers"],
        json={"residual_likelihood": "unknown", "residual_impact": "high"},
    )
    assert unknown_preview.status_code == 200
    assert unknown_preview.json()["residual_risk_score"] is None
    assert unknown_preview.json()["calculated_residual_risk_level"] is None

    archived_profile = client.post(
        f"{SCORING_BASE}/{default_profile['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "retire"},
    )
    assert archived_profile.status_code == 200
    cannot_use_archived = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-residual-risk",
        headers=org["org_headers"],
        json={
            "residual_likelihood": "low",
            "residual_impact": "low",
            "scoring_profile_id": default_profile["id"],
        },
    )
    assert cannot_use_archived.status_code == 400


def test_phase63_detail_list_summary_contract_and_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p63-summary-org1")
    org2 = bootstrap_org_user(client, email_prefix="p63-summary-org2")
    ai1 = _create_ai_system(client, org1["org_headers"], name="AI-1")
    _ = _create_scoring_profile(client, org1["org_headers"], is_default=True)
    template = _create_dimension_template(client, org1["org_headers"], is_default=True)
    assessment = _create_assessment(client, org1["org_headers"], ai1["id"], risk_level="medium")

    _ = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-dimension-template",
        headers=org1["org_headers"],
        json={"dimension_inputs_json": {"safety": {"level": "high"}, "privacy": {"level": "medium"}}},
    )
    _ = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-residual-risk",
        headers=org1["org_headers"],
        json={"residual_likelihood": "low", "residual_impact": "medium"},
    )

    listed = client.get(ASSESSMENTS_BASE, headers=org1["org_headers"])
    assert listed.status_code == 200
    row = listed.json()[0]
    assert row["dimension_template_id"] == template["id"]
    assert "dimension_score_json" in row
    assert "calculated_residual_risk_level" in row

    detail = client.get(f"{ASSESSMENTS_BASE}/{assessment['id']}", headers=org1["org_headers"])
    assert detail.status_code == 200
    dbody = detail.json()
    assert dbody["dimension_template_snapshot_json"] is not None
    assert dbody["residual_score_explanation_json"] is not None

    summary = client.get(f"{DIMENSIONS_BASE}/summary", headers=org1["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_templates"] >= 1
    assert sbody["default_template_id"] == template["id"]
    assert sbody["assessments_with_dimension_template"] >= 1
    assert "null" in sbody["by_calculated_residual_risk_level"] or sbody["by_calculated_residual_risk_level"]

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org1["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "ai_risk_dimension_templates" in groups
    assessment_fields = set(groups["ai_risk_assessments"]["response_contract_fields"])
    assert {
        "dimension_template_id",
        "dimension_template_snapshot_json",
        "dimension_inputs_json",
        "dimension_score_json",
        "dimension_weighted_score",
        "calculated_dimension_risk_level",
        "residual_likelihood",
        "residual_impact",
        "residual_risk_score",
        "calculated_residual_risk_level",
        "residual_score_explanation_json",
    }.issubset(assessment_fields)

    # tenant-scope for template access and assessment updates
    cross_template = client.get(f"{DIMENSIONS_BASE}/{template['id']}", headers=org2["org_headers"])
    assert cross_template.status_code == 404
    cross_apply = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/apply-dimension-template",
        headers=org2["org_headers"],
        json={"dimension_inputs_json": {"safety": {"level": "high"}}},
    )
    assert cross_apply.status_code == 404


def test_phase63_read_only_preview_creates_no_rows_or_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p63-readonly")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    profile = _create_scoring_profile(client, org["org_headers"], is_default=True)
    template = _create_dimension_template(client, org["org_headers"], is_default=True)

    before_assessments = db_session.execute(select(func.count(AISystemRiskAssessment.id))).scalar_one()
    before_templates = db_session.execute(select(func.count(AISystemRiskDimensionTemplate.id))).scalar_one()
    before_profiles = db_session.execute(select(func.count(AISystemRiskScoringProfile.id))).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    r1 = client.post(
        f"{DIMENSIONS_BASE}/{template['id']}/preview-score",
        headers=org["org_headers"],
        json={"dimension_inputs_json": {"safety": {"level": "high"}}},
    )
    assert r1.status_code == 200
    r2 = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/preview-residual-risk",
        headers=org["org_headers"],
        json={"residual_likelihood": "low", "residual_impact": "low", "scoring_profile_id": profile["id"]},
    )
    assert r2.status_code == 200

    after_assessments = db_session.execute(select(func.count(AISystemRiskAssessment.id))).scalar_one()
    after_templates = db_session.execute(select(func.count(AISystemRiskDimensionTemplate.id))).scalar_one()
    after_profiles = db_session.execute(select(func.count(AISystemRiskScoringProfile.id))).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    assert before_assessments == after_assessments
    assert before_templates == after_templates
    assert before_profiles == after_profiles
    assert before_audit == after_audit
