from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.models.ai_system_governance_policy_resolution_simulation_diff_report import (
    AISystemGovernancePolicyResolutionSimulationDiffReport,
)
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post("/api/v1/ai-systems", headers=headers, json={"name": name, "system_type": "agent"})
    assert response.status_code == 201
    return response.json()


def _create_pack(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 201
    return response.json()


def _create_policy_set(client, headers: dict[str, str], *, name: str, ack_text: str) -> dict:
    policy = client.post("/api/v1/ai-governance/guardrails/policy-sets", headers=headers, json={"name": name})
    assert policy.status_code == 201
    policy_body = policy.json()
    version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_body['id']}/versions",
        headers=headers,
        json={
            "profile_json": {
                "resolution_strategy": "deterministic_precedence_v1",
                "acknowledgement_text": ack_text,
                "allow_operator_override": True,
                "require_override_reason": True,
                "include_info_windows": True,
                "include_warn_windows": True,
                "include_block_windows": True,
                "scope_precedence_order": ["ai_system", "sequence_pack", "review_type", "all_ai_governance"],
            },
            "change_reason": "init",
        },
    )
    assert version.status_code == 201
    version_body = version.json()
    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_body['id']}/versions/{version_body['id']}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activate.status_code == 200
    return policy_body


def _assign_policy(client, headers: dict[str, str], payload: dict) -> None:
    response = client.post("/api/v1/ai-governance/guardrails/policy-assignments", headers=headers, json=payload)
    assert response.status_code == 201


def _persist_sim(client, headers: dict[str, str], contexts: list[dict], *, title: str) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={"persist_report": True, "title": title, "contexts": contexts},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    return body["report_id"]


def _create_diff_report_with_reason_codes(client, headers: dict[str, str]) -> str:
    ai = _create_ai_system(client, headers, name="P514 AI")
    pack = _create_pack(client, headers, name="P514 Pack")
    mapped_policy = _create_policy_set(client, headers, name="P514 Mapped", ack_text="ACK_M")
    explicit_policy = _create_policy_set(client, headers, name="P514 Explicit", ack_text="ACK_E")
    _assign_policy(
        client,
        headers,
        {"policy_set_id": mapped_policy["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "pack"},
    )

    now = datetime.now(UTC).replace(microsecond=0)
    base_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        title="base",
    )
    compare_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "explicit_policy_set_id": explicit_policy["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            },
            {
                "context_key": "ctx-2",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["periodic_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=2)).isoformat(),
            },
        ],
        title="compare",
    )
    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={
            "base_report_id": base_report_id,
            "compare_report_id": compare_report_id,
            "persist_diff": True,
            "context_match_strategy": "context_key_then_index",
        },
    )
    assert diff.status_code == 200
    return diff.json()["diff_report_id"]


def test_phase514_gating_profile_crud_and_validation(client):
    org = bootstrap_org_user(client, email_prefix="p514-profile")
    headers = org["org_headers"]

    invalid_severity = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": "bad",
            "default_severity": "urgent",
            "review_required_threshold": "medium",
            "reason_code_rules_json": {},
        },
    )
    assert invalid_severity.status_code == 422

    invalid_threshold = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": "bad2",
            "default_severity": "low",
            "review_required_threshold": "severe",
            "reason_code_rules_json": {},
        },
    )
    assert invalid_threshold.status_code == 422

    unknown_reason_code = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": "bad3",
            "default_severity": "low",
            "review_required_threshold": "medium",
            "reason_code_rules_json": {"UNKNOWN_CODE": {"severity": "high", "review_required": True}},
        },
    )
    assert unknown_reason_code.status_code == 400

    create = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": "P514 Gating",
            "default_severity": "low",
            "review_required_threshold": "high",
            "reason_code_rules_json": {
                "POLICY_SET_CHANGED": {"severity": "high", "review_required": True, "notes": "critical policy change"},
                "CONTEXT_UNCHANGED": {"severity": "info", "review_required": False},
            },
        },
    )
    assert create.status_code == 201
    profile = create.json()

    list_profiles = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
    )
    assert list_profiles.status_code == 200
    assert any(item["id"] == profile["id"] for item in list_profiles.json())

    update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile['id']}",
        headers=headers,
        json={"description": "updated", "status": "inactive"},
    )
    assert update.status_code == 200
    assert update.json()["description"] == "updated"
    assert update.json()["status"] == "inactive"

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile['id']}/archive",
        headers=headers,
        json={"reason": "cleanup"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    archived_update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles/{profile['id']}",
        headers=headers,
        json={"name": "should fail"},
    )
    assert archived_update.status_code == 400


def test_phase514_diff_classification_persist_and_audit_behavior(client):
    org = bootstrap_org_user(client, email_prefix="p514-classify")
    headers = org["org_headers"]
    diff_report_id = _create_diff_report_with_reason_codes(client, headers)

    create_profile = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": "P514 Classifier",
            "default_severity": "low",
            "review_required_threshold": "critical",
            "reason_code_rules_json": {
                "POLICY_SET_CHANGED": {"severity": "medium", "review_required": True},
                "POLICY_VERSION_CHANGED": {"severity": "high", "review_required": False},
            },
        },
    )
    assert create_profile.status_code == 201
    profile_id = create_profile.json()["id"]

    classify_preview = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/classify",
        headers=headers,
        json={"gating_profile_id": profile_id, "persist_report": False},
    )
    assert classify_preview.status_code == 200
    preview = classify_preview.json()
    assert preview["persisted"] is False
    assert preview["gating_report_id"] is None
    assert preview["max_severity"] == "high"
    assert preview["review_required"] is True
    assert preview["reason_code_count"] > 0
    assert "read-only classification" in preview["caveat"]

    classification_map = {item["reason_code"]: item for item in preview["reason_code_classifications"]}
    assert classification_map["POLICY_SET_CHANGED"]["severity"] == "medium"
    assert classification_map["POLICY_SET_CHANGED"]["review_required"] is True
    assert classification_map["CONTEXT_CHANGED"]["severity"] == "low"
    assert preview["severity_summary"]["low"] >= 1
    assert preview["severity_summary"]["high"] >= 1

    reports_after_preview = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports",
        headers=headers,
    )
    assert reports_after_preview.status_code == 200
    assert reports_after_preview.json() == []

    logs_preview = client.get("/api/v1/audit-logs", headers=headers)
    assert logs_preview.status_code == 200
    preview_actions = {item["action"] for item in logs_preview.json()}
    assert "ai_system_governance_policy_diff_gating_report.generated" not in preview_actions

    classify_persisted = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_report_id}/classify",
        headers=headers,
        json={"gating_profile_id": profile_id, "persist_report": True},
    )
    assert classify_persisted.status_code == 200
    persisted = classify_persisted.json()
    assert persisted["persisted"] is True
    assert persisted["gating_report_id"] is not None
    assert persisted["max_severity"] == "high"
    assert persisted["review_required"] is True

    list_reports = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports"
        f"?gating_profile_id={profile_id}&review_required=true&max_severity=high",
        headers=headers,
    )
    assert list_reports.status_code == 200
    assert any(item["id"] == persisted["gating_report_id"] for item in list_reports.json())

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{persisted['gating_report_id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == persisted["gating_report_id"]

    logs_final = client.get("/api/v1/audit-logs", headers=headers)
    assert logs_final.status_code == 200
    final_actions = {item["action"] for item in logs_final.json()}
    assert "ai_system_governance_policy_diff_gating_report.generated" in final_actions


def test_phase514_no_reason_code_path_tenant_scope_archive_and_summary(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p514-org1")
    org2 = bootstrap_org_user(client, email_prefix="p514-org2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    diff_id_org1 = _create_diff_report_with_reason_codes(client, h1)
    _create_diff_report_with_reason_codes(client, h2)

    row = db_session.execute(
        select(AISystemGovernancePolicyResolutionSimulationDiffReport).where(
            AISystemGovernancePolicyResolutionSimulationDiffReport.id == UUID(diff_id_org1)
        )
    ).scalar_one()
    row.reason_code_summary_json = {}
    row.reason_code_count = 0
    db_session.flush()

    profile = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=h1,
        json={
            "name": "P514 Empty",
            "default_severity": "critical",
            "review_required_threshold": "low",
            "reason_code_rules_json": {},
        },
    )
    assert profile.status_code == 201
    profile_id = profile.json()["id"]

    empty_preview = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_id_org1}/classify",
        headers=h1,
        json={"gating_profile_id": profile_id, "persist_report": False},
    )
    assert empty_preview.status_code == 200
    body = empty_preview.json()
    assert body["reason_code_count"] == 0
    assert body["max_severity"] == "info"
    assert body["review_required"] is False

    persisted = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_id_org1}/classify",
        headers=h1,
        json={"gating_profile_id": profile_id, "persist_report": True},
    )
    assert persisted.status_code == 200
    report_id = persisted.json()["gating_report_id"]

    cross_tenant_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{report_id}",
        headers=h2,
    )
    assert cross_tenant_detail.status_code == 404

    cross_tenant_profile_list = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=h2,
    )
    assert cross_tenant_profile_list.status_code == 200
    assert all(item["id"] != profile_id for item in cross_tenant_profile_list.json())

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-reports/{report_id}/archive",
        headers=h1,
        json={"reason": "complete"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    summary = client.get("/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-summary", headers=h1)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["active_profiles"] >= 1
    assert summary_body["total_gating_reports"] >= 1
    assert summary_body["archived_gating_reports"] >= 1
    assert "info" in summary_body["by_max_severity"]

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_profile.created" in actions
    assert "ai_system_governance_policy_diff_gating_report.generated" in actions
    assert "ai_system_governance_policy_diff_gating_report.archived" in actions
