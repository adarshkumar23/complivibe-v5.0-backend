import uuid
from datetime import timedelta

from sqlalchemy import func, select

from app.models.ai_system_risk_assessment import AISystemRiskAssessment
from app.models.audit_log import AuditLog
from app.models.governance_signal import GovernanceSignal
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_risk_classification_phase64 import (
    ASSESSMENTS_BASE,
    CLASSIFICATION_BASE,
    _create_ai_system,
    _create_assessment,
    _create_taxonomy,
)
from tests.unit.test_ai_system_risk_classification_review_signals_phase65 import _create_classification

PRIORITIZED_ENDPOINT = "/api/v1/ai-governance/signals/prioritized"
GROUPS_ENDPOINT = "/api/v1/ai-governance/signals/groups"
SUMMARY_ENDPOINT = "/api/v1/ai-governance/signals/priority-summary"


def _create_review_signals(client, headers: dict[str, str], classification_id: str) -> list[dict]:
    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/submit-for-review",
        headers=headers,
        json={},
    )
    assert submit.status_code == 200
    reviewed = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/mark-reviewed",
        headers=headers,
        json={},
    )
    assert reviewed.status_code == 200
    rejected = client.post(
        f"{CLASSIFICATION_BASE}/{classification_id}/reject",
        headers=headers,
        json={"rejection_reason": "manual rejection"},
    )
    assert rejected.status_code == 200
    listed = client.get("/api/v1/ai-governance/signals", headers=headers)
    assert listed.status_code == 200
    return listed.json()


def test_phase66_prioritized_signals_order_and_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p66-priority-order")
    ai = _create_ai_system(client, org["org_headers"], name="P66-AI")
    assessment = _create_assessment(
        client,
        org["org_headers"],
        ai["id"],
        risk_level="medium",
        likelihood="high",
        impact="high",
    )
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"], confidence_level="medium")
    _create_review_signals(client, org["org_headers"], classification["id"])

    before_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    prioritized = client.get(PRIORITIZED_ENDPOINT, headers=org["org_headers"])
    assert prioritized.status_code == 200
    rows = prioritized.json()
    assert len(rows) >= 3
    scores = [float(row["priority_score"]) for row in rows]
    assert scores == sorted(scores, reverse=True)
    assert rows[0]["severity"] == "critical"
    after_audit = int(db_session.execute(select(func.count(AuditLog.id))).scalar_one())
    assert before_audit == after_audit


def test_phase66_age_and_priority_band_deterministic(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p66-age")
    ai = _create_ai_system(client, org["org_headers"], name="P66-AI-Age")
    assessment = _create_assessment(client, org["org_headers"], ai["id"], risk_level="low")
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"])

    submit = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/submit-for-review",
        headers=org["org_headers"],
        json={},
    )
    assert submit.status_code == 200
    old_signal = db_session.execute(
        select(GovernanceSignal).where(
            GovernanceSignal.organization_id == uuid.UUID(org["organization_id"]),
            GovernanceSignal.signal_type == "classification_needs_review",
        )
    ).scalar_one()
    old_signal.created_at = old_signal.created_at - timedelta(days=10)
    old_signal.updated_at = old_signal.created_at
    db_session.commit()

    changes = client.post(
        f"{CLASSIFICATION_BASE}/{classification['id']}/request-changes",
        headers=org["org_headers"],
        json={"change_request_note": "new change"},
    )
    assert changes.status_code == 200

    resp = client.get(f"{PRIORITIZED_ENDPOINT}?severity=warning", headers=org["org_headers"])
    assert resp.status_code == 200
    warning_rows = resp.json()
    assert len(warning_rows) >= 2
    old = next(row for row in warning_rows if row["signal_type"] == "classification_needs_review")
    new = next(row for row in warning_rows if row["signal_type"] == "classification_changes_requested")
    assert float(old["priority_score"]) > float(new["priority_score"])

    for row in warning_rows:
        score = float(row["priority_score"])
        if score <= 24:
            expected = "low"
        elif score <= 59:
            expected = "medium"
        elif score <= 99:
            expected = "high"
        else:
            expected = "urgent"
        assert row["priority_band"] == expected


def test_phase66_risk_context_and_density_increase_priority(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p66-risk-density")
    _create_taxonomy(client, org["org_headers"], is_default=True)

    ai_low = _create_ai_system(client, org["org_headers"], name="P66-AI-Low")
    a_low = _create_assessment(client, org["org_headers"], ai_low["id"], risk_level="low")
    c_low = _create_classification(client, org["org_headers"], a_low["id"])
    client.post(
        f"{CLASSIFICATION_BASE}/{c_low['id']}/submit-for-review",
        headers=org["org_headers"],
        json={},
    )

    ai_critical = _create_ai_system(client, org["org_headers"], name="P66-AI-Critical")
    a_critical = _create_assessment(client, org["org_headers"], ai_critical["id"], risk_level="critical")
    assessment_row = db_session.execute(
        select(AISystemRiskAssessment).where(AISystemRiskAssessment.id == uuid.UUID(a_critical["id"]))
    ).scalar_one()
    assessment_row.calculated_residual_risk_level = "high"
    db_session.commit()
    c_critical = _create_classification(client, org["org_headers"], a_critical["id"])
    client.post(
        f"{CLASSIFICATION_BASE}/{c_critical['id']}/submit-for-review",
        headers=org["org_headers"],
        json={},
    )

    # Add extra open signal on critical system to increase density.
    client.post(
        f"{CLASSIFICATION_BASE}/{c_critical['id']}/request-changes",
        headers=org["org_headers"],
        json={"change_request_note": "density"},
    )

    rows = client.get(
        f"{PRIORITIZED_ENDPOINT}?signal_type=classification_needs_review&severity=warning",
        headers=org["org_headers"],
    )
    assert rows.status_code == 200
    body = rows.json()
    assert len(body) >= 2
    by_ai = {row["related_ai_system_id"]: row for row in body}
    assert float(by_ai[ai_critical["id"]]["priority_score"]) > float(by_ai[ai_low["id"]]["priority_score"])


def test_phase66_groups_endpoint_and_filters(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p66-groups")
    ai = _create_ai_system(client, org["org_headers"], name="P66-AI-Groups")
    assessment = _create_assessment(client, org["org_headers"], ai["id"])
    _create_taxonomy(client, org["org_headers"], is_default=True)
    classification = _create_classification(client, org["org_headers"], assessment["id"])
    _create_review_signals(client, org["org_headers"], classification["id"])

    filtered = client.get(f"{PRIORITIZED_ENDPOINT}?severity=critical", headers=org["org_headers"])
    assert filtered.status_code == 200
    for row in filtered.json():
        assert row["severity"] == "critical"

    groups = client.get(GROUPS_ENDPOINT, headers=org["org_headers"])
    assert groups.status_code == 200
    gbody = groups.json()
    assert gbody
    assert gbody[0]["signal_count"] >= 1
    assert "critical" in gbody[0]["severities_count"] or "warning" in gbody[0]["severities_count"]
    assert gbody[0]["signals"]


def test_phase66_ai_system_attention_and_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p66-attn-1")
    org2 = bootstrap_org_user(client, email_prefix="p66-attn-2")

    ai = _create_ai_system(client, org1["org_headers"], name="P66-AI-Attn")
    assessment = _create_assessment(client, org1["org_headers"], ai["id"], risk_level="high")
    _create_taxonomy(client, org1["org_headers"], is_default=True)
    classification = _create_classification(client, org1["org_headers"], assessment["id"])
    _create_review_signals(client, org1["org_headers"], classification["id"])

    attention = client.get(f"/api/v1/ai-governance/ai-systems/{ai['id']}/attention", headers=org1["org_headers"])
    assert attention.status_code == 200
    body = attention.json()
    assert body["ai_system_id"] == ai["id"]
    assert body["open_signal_count"] >= 1
    assert body["top_signals"]
    assert body["latest_risk_assessment_id"] == assessment["id"]

    cross = client.get(f"/api/v1/ai-governance/ai-systems/{ai['id']}/attention", headers=org2["org_headers"])
    assert cross.status_code == 404


def test_phase66_priority_summary_and_explanation_and_no_mutation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p66-summary-1")
    org2 = bootstrap_org_user(client, email_prefix="p66-summary-2")

    ai = _create_ai_system(client, org1["org_headers"], name="P66-AI-Summary")
    assessment = _create_assessment(client, org1["org_headers"], ai["id"])
    _create_taxonomy(client, org1["org_headers"], is_default=True)
    classification = _create_classification(client, org1["org_headers"], assessment["id"])
    signals = _create_review_signals(client, org1["org_headers"], classification["id"])

    before = {
        row["id"]: row["status"]
        for row in client.get("/api/v1/ai-governance/signals?status=open", headers=org1["org_headers"]).json()
    }

    summary = client.get(SUMMARY_ENDPOINT, headers=org1["org_headers"])
    assert summary.status_code == 200
    sbody = summary.json()
    assert sbody["total_open_signals"] >= 1
    assert "urgent_signal_count" in sbody
    assert isinstance(sbody["top_ai_systems_by_attention"], list)

    signal_id = signals[0]["id"]
    explanation = client.get(
        f"/api/v1/ai-governance/signals/{signal_id}/priority-explanation",
        headers=org1["org_headers"],
    )
    assert explanation.status_code == 200
    ebody = explanation.json()
    for key in (
        "base_severity_weight",
        "age_weight",
        "entity_risk_context_weight",
        "signal_density_weight",
        "total_priority_score",
        "priority_band",
        "source_fields",
    ):
        assert key in ebody

    cross = client.get(
        f"/api/v1/ai-governance/signals/{signal_id}/priority-explanation",
        headers=org2["org_headers"],
    )
    assert cross.status_code == 404

    after = {
        row["id"]: row["status"]
        for row in client.get("/api/v1/ai-governance/signals?status=open", headers=org1["org_headers"]).json()
    }
    assert before == after


def test_phase66_contract_group_and_fields_present(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p66-contract")
    contracts = client.get("/api/v1/ai-governance/contracts/phase6", headers=org["org_headers"])
    assert contracts.status_code == 200
    groups = {g["group_key"]: g for g in contracts.json()["groups"]}
    assert "governance_signal_prioritization" in groups
    signal_fields = set(groups["governance_signals"]["response_contract_fields"])
    assert {"priority_score", "priority_band", "priority_explanation_json", "group_key"}.issubset(signal_fields)
