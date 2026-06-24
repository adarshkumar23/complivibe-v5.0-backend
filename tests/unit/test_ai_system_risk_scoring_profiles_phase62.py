from sqlalchemy import func, select

from app.models.ai_system import AISystem
from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.ai_system_risk_scoring_profile import AISystemRiskScoringProfile
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user

ASSESSMENTS_BASE = "/api/v1/ai-governance/ai-risk/assessments"
PROFILES_BASE = "/api/v1/ai-governance/ai-risk/scoring-profiles"


def _create_ai_system(client, headers: dict[str, str], *, name: str = "Risk-Profile AI") -> dict:
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


def _create_profile(client, headers: dict[str, str], **overrides) -> dict:
    payload = {"name": "Default Profile"}
    payload.update(overrides)
    response = client.post(PROFILES_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase62_profile_crud_defaults_validation_and_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p62-profile-org1")
    org2 = bootstrap_org_user(client, email_prefix="p62-profile-org2")

    created = _create_profile(client, org1["org_headers"], is_default=True)
    assert created["status"] == "active"
    assert created["is_default"] is True
    assert created["likelihood_weights_json"]["critical"] == 4
    assert created["risk_level_thresholds_json"][0]["risk_level"] == "low"

    custom = _create_profile(
        client,
        org1["org_headers"],
        name="Custom",
        likelihood_weights_json={"unknown": None, "low": 1, "medium": 3, "high": 5, "critical": 8},
        impact_weights_json={"unknown": None, "low": 1, "medium": 2, "high": 4, "critical": 7},
        risk_level_thresholds_json=[
            {"min_score": 1, "max_score": 4, "risk_level": "low"},
            {"min_score": 5, "max_score": 9, "risk_level": "medium"},
            {"min_score": 10, "max_score": 20, "risk_level": "high"},
            {"min_score": 21, "max_score": 56, "risk_level": "critical"},
        ],
        is_default=False,
    )
    assert custom["name"] == "Custom"
    assert custom["is_default"] is False

    invalid_weights = client.post(
        PROFILES_BASE,
        headers=org1["org_headers"],
        json={"name": "Invalid", "likelihood_weights_json": {"low": 1}},
    )
    assert invalid_weights.status_code == 400

    overlapping = client.post(
        PROFILES_BASE,
        headers=org1["org_headers"],
        json={
            "name": "Overlap",
            "risk_level_thresholds_json": [
                {"min_score": 1, "max_score": 6, "risk_level": "low"},
                {"min_score": 6, "max_score": 10, "risk_level": "medium"},
            ],
        },
    )
    assert overlapping.status_code == 400

    listed = client.get(PROFILES_BASE, headers=org1["org_headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    cross_org_get = client.get(f"{PROFILES_BASE}/{created['id']}", headers=org2["org_headers"])
    assert cross_org_get.status_code == 404


def test_phase62_default_set_archive_and_update_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p62-default")
    p1 = _create_profile(client, org["org_headers"], name="P1", is_default=True)
    p2 = _create_profile(client, org["org_headers"], name="P2", is_default=False)

    set_default = client.post(f"{PROFILES_BASE}/{p2['id']}/set-default", headers=org["org_headers"], json={})
    assert set_default.status_code == 200
    assert set_default.json()["is_default"] is True

    p1_after = client.get(f"{PROFILES_BASE}/{p1['id']}", headers=org["org_headers"])
    assert p1_after.status_code == 200
    assert p1_after.json()["is_default"] is False

    missing_reason = client.post(f"{PROFILES_BASE}/{p1['id']}/archive", headers=org["org_headers"], json={})
    assert missing_reason.status_code == 422

    archive_default_blocked = client.post(
        f"{PROFILES_BASE}/{p2['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "should block while default with active alternatives"},
    )
    assert archive_default_blocked.status_code == 400

    # Revert default to p1, then archive p2.
    back_to_p1 = client.post(f"{PROFILES_BASE}/{p1['id']}/set-default", headers=org["org_headers"], json={})
    assert back_to_p1.status_code == 200
    archived = client.post(f"{PROFILES_BASE}/{p2['id']}/archive", headers=org["org_headers"], json={"reason": "retired"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    update_archived = client.patch(f"{PROFILES_BASE}/{p2['id']}", headers=org["org_headers"], json={"name": "Nope"})
    assert update_archived.status_code == 400


def test_phase62_preview_read_only_and_deterministic(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p62-preview")
    profile = _create_profile(client, org["org_headers"], is_default=True)
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    preview = client.post(
        f"{PROFILES_BASE}/{profile['id']}/preview-score",
        headers=org["org_headers"],
        json={"likelihood": "high", "impact": "medium"},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["inherent_risk_score"] == 6
    assert body["calculated_risk_level"] == "medium"
    assert body["score_explanation"]["algorithm"] == "manual_profile_weighted_v1"
    assert "deterministic presentation output" in body["caveat"]

    unknown = client.post(
        f"{PROFILES_BASE}/{profile['id']}/preview-score",
        headers=org["org_headers"],
        json={"likelihood": "unknown", "impact": "high"},
    )
    assert unknown.status_code == 200
    assert unknown.json()["inherent_risk_score"] is None
    assert unknown.json()["calculated_risk_level"] is None

    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_audit == before_audit


def test_phase62_recalculate_uses_explicit_or_default_and_manual_vs_calculated(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p62-recalc")
    ai = _create_ai_system(client, org["org_headers"])
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="high", likelihood="high", impact="high")
    default_profile = _create_profile(client, org["org_headers"], name="Default", is_default=True)
    explicit_profile = _create_profile(
        client,
        org["org_headers"],
        name="Explicit",
        likelihood_weights_json={"unknown": None, "low": 1, "medium": 2, "high": 4, "critical": 6},
        impact_weights_json={"unknown": None, "low": 1, "medium": 2, "high": 3, "critical": 5},
        risk_level_thresholds_json=[
            {"min_score": 1, "max_score": 4, "risk_level": "low"},
            {"min_score": 5, "max_score": 8, "risk_level": "medium"},
            {"min_score": 9, "max_score": 15, "risk_level": "high"},
            {"min_score": 16, "max_score": 30, "risk_level": "critical"},
        ],
    )

    recalc_explicit = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/recalculate-score",
        headers=org["org_headers"],
        json={"scoring_profile_id": explicit_profile["id"]},
    )
    assert recalc_explicit.status_code == 200
    body = recalc_explicit.json()
    assert body["scoring_profile_id"] == explicit_profile["id"]
    assert body["inherent_risk_score"] == 12
    assert body["calculated_risk_level"] == "high"
    assert body["risk_level"] == "high"  # manual stays as-is by default
    assert body["score_explanation_json"] is not None
    assert body["scoring_profile_snapshot_json"]["name"] == "Explicit"

    recalc_default = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/recalculate-score",
        headers=org["org_headers"],
        json={},
    )
    assert recalc_default.status_code == 200
    assert recalc_default.json()["scoring_profile_id"] == default_profile["id"]

    recalc_apply = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/recalculate-score",
        headers=org["org_headers"],
        json={"scoring_profile_id": explicit_profile["id"], "apply_calculated_risk_level_to_manual_risk_level": True},
    )
    assert recalc_apply.status_code == 200
    assert recalc_apply.json()["risk_level"] == recalc_apply.json()["calculated_risk_level"]

    archived_profile = client.post(
        f"{PROFILES_BASE}/{explicit_profile['id']}/archive",
        headers=org["org_headers"],
        json={"reason": "do not use"},
    )
    assert archived_profile.status_code == 200
    cannot_use_archived = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/recalculate-score",
        headers=org["org_headers"],
        json={"scoring_profile_id": explicit_profile["id"]},
    )
    assert cannot_use_archived.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=org["org_headers"])
    assert logs.status_code == 200
    actions = [row["action"] for row in logs.json()]
    assert "ai_system_risk_assessment.score_recalculated" in actions


def test_phase62_assessment_scoring_fields_and_summary_and_contracts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p62-summary")
    ai = _create_ai_system(client, org["org_headers"], name="SummaryAI")
    assessment = _create_assessment(client, org["org_headers"], ai["id"], likelihood="unknown", impact="high", risk_level="medium")
    profile = _create_profile(client, org["org_headers"], is_default=True)

    recalc = client.post(
        f"{ASSESSMENTS_BASE}/{assessment['id']}/recalculate-score",
        headers=org["org_headers"],
        json={},
    )
    assert recalc.status_code == 200
    recalc_body = recalc.json()
    assert recalc_body["inherent_risk_score"] is None
    assert recalc_body["calculated_risk_level"] is None
    assert recalc_body["risk_level"] == "medium"
    assert recalc_body["scoring_profile_id"] == profile["id"]
    assert recalc_body["score_explanation_json"]["unknown_input"] is True

    listed = client.get(ASSESSMENTS_BASE, headers=org["org_headers"])
    assert listed.status_code == 200
    assert listed.json()[0]["scoring_profile_id"] == profile["id"]
    assert "score_explanation_json" in listed.json()[0]

    summary = client.get(f"{PROFILES_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_profiles"] >= 1
    assert sbody["default_profile_id"] == profile["id"]
    assert sbody["assessments_with_scoring_profile"] >= 1
    assert "null" in sbody["by_calculated_risk_level"]

    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "ai_risk_assessments" in groups
    assert "ai_risk_scoring_profiles" in groups
    assessment_fields = set(groups["ai_risk_assessments"]["response_contract_fields"])
    assert {"scoring_profile_id", "scoring_profile_snapshot_json", "score_explanation_json", "calculated_risk_level", "inherent_risk_score", "risk_level"}.issubset(assessment_fields)


def test_phase62_phase61_routes_documented_and_recalc_tenant_scope(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p62-docs-org1")
    org2 = bootstrap_org_user(client, email_prefix="p62-docs-org2")

    ai2 = _create_ai_system(client, org2["org_headers"])
    a2 = _create_assessment(client, org2["org_headers"], ai2["id"])
    p2 = _create_profile(client, org2["org_headers"], is_default=True)
    _ = p2

    cross_recalc = client.post(
        f"{ASSESSMENTS_BASE}/{a2['id']}/recalculate-score",
        headers=org1["org_headers"],
        json={},
    )
    assert cross_recalc.status_code == 404

    with open("README.md", encoding="utf-8") as handle:
        readme = handle.read()
    assert "POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/archive" in readme
    assert "POST /api/v1/ai-governance/ai-risk/assessments/{assessment_id}/snapshots" in readme

    # Ensure no governance source records are mutated by read-only profile list/get.
    before_assessment_count = db_session.execute(select(func.count(AISystemRiskAssessment.id))).scalar_one()
    before_ai_count = db_session.execute(select(func.count(AISystem.id))).scalar_one()
    before_profile_count = db_session.execute(select(func.count(AISystemRiskScoringProfile.id))).scalar_one()
    _ = client.get(PROFILES_BASE, headers=org1["org_headers"])
    after_assessment_count = db_session.execute(select(func.count(AISystemRiskAssessment.id))).scalar_one()
    after_ai_count = db_session.execute(select(func.count(AISystem.id))).scalar_one()
    after_profile_count = db_session.execute(select(func.count(AISystemRiskScoringProfile.id))).scalar_one()
    assert before_assessment_count == after_assessment_count
    assert before_ai_count == after_ai_count
    assert before_profile_count == after_profile_count
