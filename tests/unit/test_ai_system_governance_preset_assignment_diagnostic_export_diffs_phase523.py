from sqlalchemy import func, select

from app.models.ai_system_governance_preset_assignment_diagnostic_export import (
    AISystemGovernancePresetAssignmentDiagnosticExport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_reports_phase521 import (
    _create_assignment,
    _persist_coverage_report,
)
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519 import _create_context
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset


def _export_report(client, headers: dict[str, str], report_id: str) -> dict:
    response = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/export",
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _export_diff_report(client, headers: dict[str, str], diff_report_id: str) -> dict:
    response = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/export",
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()


def _persist_diag_diff(client, headers: dict[str, str], base_report_id: str, compare_report_id: str) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=headers,
        json={"base_report_id": base_report_id, "compare_report_id": compare_report_id, "persist_diff": True},
    )
    assert response.status_code == 200
    return response.json()["diff_report_id"]


def test_phase523_export_diff_report_exports_no_persist_and_persisted(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p523-report")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})

    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}, {"context_key": "removed"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="b")
    exp_a = _export_report(client, headers, report_a)
    exp_b = _export_report(client, headers, report_b)

    before_diff_count = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id))
    ).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    no_persist = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=headers,
        json={
            "base_export_id": exp_a["export_id"],
            "compare_export_id": exp_b["export_id"],
            "persist_diff": False,
        },
    )
    assert no_persist.status_code == 200
    body = no_persist.json()
    assert body["persisted"] is False
    assert body["export_diff_report_id"] is None
    assert body["export_type"] == "diagnostic_report"
    assert body["payload_hash_changed"] is True
    assert body["removed_paths_count"] >= 1
    assert body["changed_paths_count"] >= 1
    assert body["base_verification"]["valid_signature"] is True
    assert body["compare_verification"]["valid_signature"] is True
    unchanged_once = body["unchanged_paths_count"]

    repeat = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=headers,
        json={
            "base_export_id": exp_a["export_id"],
            "compare_export_id": exp_b["export_id"],
            "persist_diff": False,
        },
    )
    assert repeat.status_code == 200
    assert repeat.json()["unchanged_paths_count"] == unchanged_once

    after_diff_count = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id))
    ).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_diff_count == before_diff_count
    assert after_audit == before_audit

    persisted = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=headers,
        json={
            "base_export_id": exp_a["export_id"],
            "compare_export_id": exp_b["export_id"],
            "title": "persist",
            "persist_diff": True,
        },
    )
    assert persisted.status_code == 200
    persisted_body = persisted.json()
    assert persisted_body["persisted"] is True
    assert persisted_body["export_diff_report_id"] is not None


def test_phase523_export_diff_diagnostic_diff_exports_and_revoked_trust(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p523-diff")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})

    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}, {"context_key": "b"}], title="b")
    report_c = _persist_coverage_report(client, headers, contexts=[{"context_key": "a", "rollout_class": "x"}], title="c")
    diag_diff_1 = _persist_diag_diff(client, headers, report_a, report_b)
    diag_diff_2 = _persist_diag_diff(client, headers, report_b, report_c)

    exp_diff_1 = _export_diff_report(client, headers, diag_diff_1)
    exp_diff_2 = _export_diff_report(client, headers, diag_diff_2)

    revoke = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{exp_diff_2['export_id']}/revoke",
        headers=headers,
        json={"reason": "revoke source"},
    )
    assert revoke.status_code == 200

    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=headers,
        json={
            "base_export_id": exp_diff_1["export_id"],
            "compare_export_id": exp_diff_2["export_id"],
            "persist_diff": False,
        },
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["export_type"] == "diagnostic_diff_report"
    assert body["base_verification"]["valid_signature"] is True
    assert body["compare_verification"]["valid_signature"] is True
    assert body["base_verification"]["trusted"] is True
    assert body["compare_verification"]["trusted"] is False
    assert body["added_paths_count"] >= 0
    assert body["changed_paths_count"] >= 1


def test_phase523_export_diff_type_mismatch_tenant_scope_list_get_archive_summary(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p523-t1")
    org2 = bootstrap_org_user(client, email_prefix="p523-t2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    p1, b1, _ = _create_context(client, db_session, h1, org1["organization_id"])
    p2, b2, _ = _create_context(client, db_session, h2, org2["organization_id"])
    preset1 = _create_preset(client, h1, baseline_report_id=b1, profile_id=p1)
    preset2 = _create_preset(client, h2, baseline_report_id=b2, profile_id=p2)
    _create_assignment(client, h1, {"preset_id": preset1["id"], "scope_type": "all_ai_governance", "reason": "g1"})
    _create_assignment(client, h2, {"preset_id": preset2["id"], "scope_type": "all_ai_governance", "reason": "g2"})

    r1a = _persist_coverage_report(client, h1, contexts=[{"context_key": "a"}], title="r1a")
    r1b = _persist_coverage_report(client, h1, contexts=[{"context_key": "b"}], title="r1b")
    r2a = _persist_coverage_report(client, h2, contexts=[{"context_key": "a"}], title="r2a")
    e_report_a = _export_report(client, h1, r1a)
    e_report_b = _export_report(client, h1, r1b)
    e_report_other_org = _export_report(client, h2, r2a)

    diag_diff = _persist_diag_diff(client, h1, r1a, r1b)
    e_diff = _export_diff_report(client, h1, diag_diff)

    mismatch = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=h1,
        json={"base_export_id": e_report_a["export_id"], "compare_export_id": e_diff["export_id"]},
    )
    assert mismatch.status_code == 400

    bad_base = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=h1,
        json={"base_export_id": e_report_other_org["export_id"], "compare_export_id": e_report_b["export_id"]},
    )
    assert bad_base.status_code == 404

    bad_compare = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=h1,
        json={"base_export_id": e_report_a["export_id"], "compare_export_id": e_report_other_org["export_id"]},
    )
    assert bad_compare.status_code == 404

    persisted = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=h1,
        json={"base_export_id": e_report_a["export_id"], "compare_export_id": e_report_b["export_id"], "persist_diff": True},
    )
    assert persisted.status_code == 200
    diff_report_id = persisted.json()["export_diff_report_id"]

    list_reports = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports",
        headers=h1,
    )
    assert list_reports.status_code == 200
    assert any(item["id"] == diff_report_id for item in list_reports.json())

    cross_get = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{diff_report_id}",
        headers=h2,
    )
    assert cross_get.status_code == 404

    detail_before = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{e_report_a['export_id']}",
        headers=h1,
    )
    assert detail_before.status_code == 200
    payload_before = detail_before.json()["export_payload_json"]

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{diff_report_id}/archive",
        headers=h1,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    detail_after = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{e_report_a['export_id']}",
        headers=h1,
    )
    assert detail_after.status_code == 200
    assert detail_after.json()["export_payload_json"] == payload_before

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-summary",
        headers=h1,
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_export_diff_reports"] >= 1
    assert s["archived_export_diff_reports"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_preset_assignment_diagnostic_export_diff.generated" in actions
    assert "ai_system_governance_preset_assignment_diagnostic_export_diff.archived" in actions


def test_phase523_no_files_and_no_persist_side_effects(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p523-nofile")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})
    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "b"}], title="b")
    exp_a = _export_report(client, headers, report_a)
    exp_b = _export_report(client, headers, report_b)

    before_count = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id))
    ).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    before_exports = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id))).scalar_one()
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=headers,
        json={"base_export_id": exp_a["export_id"], "compare_export_id": exp_b["export_id"], "persist_diff": False},
    )
    assert response.status_code == 200
    after_count = db_session.execute(
        select(func.count(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id))
    ).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    after_exports = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id))).scalar_one()
    assert after_count == before_count
    assert after_audit == before_audit
    assert after_exports == before_exports
