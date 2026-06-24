from sqlalchemy import func, select

from app.models.ai_system_governance_policy_diff_gating_compare_preset_assignment import (
    AISystemGovernancePolicyDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_policy_diff_gating_compare_preset_assignment_history import (
    AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticDiffReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_report import (
    AISystemGovernancePresetAssignmentDiagnosticReport,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519 import _create_context
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset


def _create_assignment(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _persist_coverage_report(client, headers: dict[str, str], *, contexts: list[dict], title: str) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=headers,
        json={"title": title, "persist_report": True, "contexts": contexts},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["report_id"] is not None
    return body["report_id"]


def test_phase521_coverage_reports_read_only_default_and_persisted_flow(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p521-reports")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(
        client,
        headers,
        {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )

    before_reports = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id))
    ).scalar_one()
    before_assignments = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    before_history = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    no_persist = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=headers,
        json={"contexts": [{"context_key": "ctx-1"}], "persist_report": False},
    )
    assert no_persist.status_code == 200
    no_persist_body = no_persist.json()
    assert no_persist_body["persisted"] is False
    assert no_persist_body["report_id"] is None

    after_reports = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id))
    ).scalar_one()
    after_assignments = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    after_history = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_reports == before_reports
    assert after_assignments == before_assignments
    assert after_history == before_history
    assert after_audit == before_audit

    persisted = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/coverage-diagnostics",
        headers=headers,
        json={
            "title": "P521 Coverage Snapshot",
            "description": "snapshot",
            "persist_report": True,
            "contexts": [{"context_key": "ctx-1"}, {"context_key": "ctx-2"}],
        },
    )
    assert persisted.status_code == 200
    persisted_body = persisted.json()
    assert persisted_body["persisted"] is True
    assert persisted_body["report_id"] is not None
    report_id = persisted_body["report_id"]

    list_reports = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports",
        headers=headers,
    )
    assert list_reports.status_code == 200
    assert any(item["id"] == report_id for item in list_reports.json())

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["id"] == report_id
    assert detail_body["input_contexts_json"][0]["context_key"] == "ctx-1"
    assert detail_body["result_json"]["context_count"] == 2

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_preset_assignment_diagnostic_report.generated" in actions
    assert "ai_system_governance_preset_assignment_diagnostic_report.archived" in actions


def test_phase521_diagnostic_diff_no_persist_and_persisted_diffability(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p521-diff")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset_active = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_inactive = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    set_inactive = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_inactive['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert set_inactive.status_code == 200
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_active["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )

    base_report_id = _persist_coverage_report(
        client,
        headers,
        contexts=[{"context_key": "ctx-a"}, {"context_key": "ctx-removed"}],
        title="base",
    )
    compare_report_id = _persist_coverage_report(
        client,
        headers,
        contexts=[
            {"context_key": "ctx-a", "explicit_preset_id": preset_inactive["id"]},
            {"context_key": "ctx-added"},
        ],
        title="compare",
    )

    before_diff_count = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id))
    ).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    no_persist_diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=headers,
        json={
            "base_report_id": base_report_id,
            "compare_report_id": compare_report_id,
            "persist_diff": False,
            "context_match_strategy": "context_key_only",
        },
    )
    assert no_persist_diff.status_code == 200
    no_persist_body = no_persist_diff.json()
    assert no_persist_body["persisted"] is False
    assert no_persist_body["diff_report_id"] is None
    assert no_persist_body["added_contexts_count"] == 1
    assert no_persist_body["removed_contexts_count"] == 1
    assert no_persist_body["changed_contexts_count"] >= 1
    assert no_persist_body["diagnostic_code_changes_count"] >= 1
    matched = [item for item in no_persist_body["context_diffs"] if item["match_type"] == "matched"]
    assert any(change["field_path"] == "resolved_preset_id" for item in matched for change in item["field_changes"])
    assert any(change["field_path"] == "resolution_source" for item in matched for change in item["field_changes"])
    assert any(change["field_path"] == "severity" for item in matched for change in item["field_changes"])
    assert any(change["field_path"] == "diagnostic_codes" for item in matched for change in item["field_changes"])
    assert any(change["field_path"] == "precedence_trace" for item in matched for change in item["field_changes"])

    after_diff_count = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id))
    ).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_diff_count == before_diff_count
    assert after_audit == before_audit

    persist_diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=headers,
        json={
            "base_report_id": base_report_id,
            "compare_report_id": compare_report_id,
            "persist_diff": True,
            "title": "P521 Diagnostic Diff",
            "context_match_strategy": "context_key_only",
        },
    )
    assert persist_diff.status_code == 200
    persist_diff_body = persist_diff.json()
    assert persist_diff_body["persisted"] is True
    assert persist_diff_body["diff_report_id"] is not None
    diff_report_id = persist_diff_body["diff_report_id"]

    list_diff = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports",
        headers=headers,
    )
    assert list_diff.status_code == 200
    assert any(item["id"] == diff_report_id for item in list_diff.json())

    detail_diff = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}",
        headers=headers,
    )
    assert detail_diff.status_code == 200
    assert detail_diff.json()["id"] == diff_report_id

    before_base_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{base_report_id}",
        headers=headers,
    )
    assert before_base_detail.status_code == 200
    before_snapshot = before_base_detail.json()["result_json"]
    _ = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=headers,
        json={"base_report_id": base_report_id, "compare_report_id": compare_report_id, "persist_diff": False},
    )
    after_base_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{base_report_id}",
        headers=headers,
    )
    assert after_base_detail.status_code == 200
    assert after_base_detail.json()["result_json"] == before_snapshot

    archive_diff = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archive_diff.status_code == 200
    assert archive_diff.json()["status"] == "archived"

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_preset_assignment_diagnostic_diff.generated" in actions
    assert "ai_system_governance_preset_assignment_diagnostic_diff.archived" in actions


def test_phase521_diagnostic_report_and_diff_tenant_isolation(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p521-tenant-1")
    org2 = bootstrap_org_user(client, email_prefix="p521-tenant-2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    profile1, base1, _ = _create_context(client, db_session, h1, org1["organization_id"])
    profile2, base2, _ = _create_context(client, db_session, h2, org2["organization_id"])
    preset1 = _create_preset(client, h1, baseline_report_id=base1, profile_id=profile1)
    preset2 = _create_preset(client, h2, baseline_report_id=base2, profile_id=profile2)
    _create_assignment(client, h1, {"preset_id": preset1["id"], "scope_type": "all_ai_governance", "reason": "g1"})
    _create_assignment(client, h2, {"preset_id": preset2["id"], "scope_type": "all_ai_governance", "reason": "g2"})

    r1a = _persist_coverage_report(client, h1, contexts=[{"context_key": "a"}], title="org1-a")
    r1b = _persist_coverage_report(client, h1, contexts=[{"context_key": "b"}], title="org1-b")
    r2a = _persist_coverage_report(client, h2, contexts=[{"context_key": "a"}], title="org2-a")

    cross_report = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{r2a}",
        headers=h1,
    )
    assert cross_report.status_code == 404

    bad_base = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=h1,
        json={"base_report_id": r2a, "compare_report_id": r1b},
    )
    assert bad_base.status_code == 404

    bad_compare = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=h1,
        json={"base_report_id": r1a, "compare_report_id": r2a},
    )
    assert bad_compare.status_code == 404


def test_phase521_diagnostic_report_summary_and_no_assignment_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p521-summary")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(
        client,
        headers,
        {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )
    before_assignments = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    before_history = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()

    report_1 = _persist_coverage_report(client, headers, contexts=[{"context_key": "ok"}], title="summary-1")
    report_2 = _persist_coverage_report(client, headers, contexts=[{"context_key": "x", "review_types": ["initial_review"]}], title="summary-2")
    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=headers,
        json={"base_report_id": report_1, "compare_report_id": report_2, "persist_diff": True},
    )
    assert diff.status_code == 200

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-report-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_reports"] >= 2
    assert body["total_diff_reports"] >= 1
    assert "caveat" in body

    after_assignments = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    after_history = db_session.execute(
        select(func.count(AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    assert after_assignments == before_assignments
    assert after_history == before_history
