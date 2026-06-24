from uuid import UUID

from sqlalchemy import func, select

from app.models.ai_system_governance_preset_assignment_diagnostic_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticDiffReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export import (
    AISystemGovernancePresetAssignmentDiagnosticExport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_report import (
    AISystemGovernancePresetAssignmentDiagnosticReport,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_reports_phase521 import (
    _create_assignment,
    _persist_coverage_report,
)
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519 import _create_context
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset


def test_phase522_export_diagnostic_report_and_verify_no_mutation(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p522-report")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})
    report_id = _persist_coverage_report(client, headers, contexts=[{"context_key": "ctx"}], title="r")

    source_before = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}",
        headers=headers,
    )
    assert source_before.status_code == 200
    source_before_json = source_before.json()

    export = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/export",
        headers=headers,
    )
    assert export.status_code == 200
    body = export.json()
    assert body["export_type"] == "diagnostic_report"
    assert body["source_report_id"] == report_id
    assert body["canonical_payload_sha256"] is not None
    assert body["signature_algorithm"] == "HMAC-SHA256"
    assert body["internal_signature"] is not None

    export_id = body["export_id"]
    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["export_payload_json"]["export_type"] == "diagnostic_report"

    verify = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/verify",
        headers=headers,
    )
    assert verify.status_code == 200
    verify_body = verify.json()
    assert verify_body["valid_hash"] is True
    assert verify_body["valid_signature"] is True
    assert verify_body["trusted"] is True

    source_after = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}",
        headers=headers,
    )
    assert source_after.status_code == 200
    assert source_after.json() == source_before_json

    export_row_before = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExport).where(
            AISystemGovernancePresetAssignmentDiagnosticExport.id == UUID(body["export_id"])
        )
    ).scalar_one()
    updated_at_before = export_row_before.updated_at
    _ = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/verify",
        headers=headers,
    )
    export_row_after = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExport).where(
            AISystemGovernancePresetAssignmentDiagnosticExport.id == UUID(body["export_id"])
        )
    ).scalar_one()
    assert export_row_after.updated_at == updated_at_before


def test_phase522_export_diagnostic_diff_and_revoke_behavior(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p522-diff")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})
    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "b"}], title="b")
    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/diff",
        headers=headers,
        json={"base_report_id": report_a, "compare_report_id": report_b, "persist_diff": True},
    )
    assert diff.status_code == 200
    diff_report_id = diff.json()["diff_report_id"]

    source_before = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}",
        headers=headers,
    )
    assert source_before.status_code == 200
    source_before_json = source_before.json()

    export = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}/export",
        headers=headers,
    )
    assert export.status_code == 200
    export_body = export.json()
    assert export_body["export_type"] == "diagnostic_diff_report"
    assert export_body["source_diff_report_id"] == diff_report_id
    export_id = export_body["export_id"]

    missing_reason = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/revoke",
        headers=headers,
        json={},
    )
    assert missing_reason.status_code == 422

    revoke = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/revoke",
        headers=headers,
        json={"reason": "retire"},
    )
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "revoked"
    assert revoke.json()["internal_signature"] == export_body["internal_signature"]
    assert revoke.json()["canonical_payload_sha256"] == export_body["canonical_payload_sha256"]

    verify = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_id}/verify",
        headers=headers,
    )
    assert verify.status_code == 200
    verify_body = verify.json()
    assert verify_body["valid_hash"] is True
    assert verify_body["valid_signature"] is True
    assert verify_body["status"] == "revoked"
    assert verify_body["trusted"] is False

    source_after = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-diff-reports/{diff_report_id}",
        headers=headers,
    )
    assert source_after.status_code == 200
    assert source_after.json() == source_before_json


def test_phase522_export_list_detail_summary_audit_and_tenant_scoping(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p522-org1")
    org2 = bootstrap_org_user(client, email_prefix="p522-org2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    p1, b1, _ = _create_context(client, db_session, h1, org1["organization_id"])
    p2, b2, _ = _create_context(client, db_session, h2, org2["organization_id"])
    preset1 = _create_preset(client, h1, baseline_report_id=b1, profile_id=p1)
    preset2 = _create_preset(client, h2, baseline_report_id=b2, profile_id=p2)
    _create_assignment(client, h1, {"preset_id": preset1["id"], "scope_type": "all_ai_governance", "reason": "g1"})
    _create_assignment(client, h2, {"preset_id": preset2["id"], "scope_type": "all_ai_governance", "reason": "g2"})
    report1 = _persist_coverage_report(client, h1, contexts=[{"context_key": "x"}], title="r1")
    report2 = _persist_coverage_report(client, h2, contexts=[{"context_key": "x"}], title="r2")

    e1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report1}/export",
        headers=h1,
    )
    assert e1.status_code == 200
    e2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report2}/export",
        headers=h2,
    )
    assert e2.status_code == 200

    list1 = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports",
        headers=h1,
    )
    assert list1.status_code == 200
    ids1 = {item["id"] for item in list1.json()}
    assert e1.json()["export_id"] in ids1
    assert e2.json()["export_id"] not in ids1

    cross_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{e2.json()['export_id']}",
        headers=h1,
    )
    assert cross_detail.status_code == 404

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-summary",
        headers=h1,
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_exports"] >= 1
    assert s["generated_exports"] >= 1
    assert s["diagnostic_report_exports"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_preset_assignment_diagnostic_export.generated" in actions


def test_phase522_no_file_external_artifact_side_effects(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p522-no-files")
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})
    report_id = _persist_coverage_report(client, headers, contexts=[{"context_key": "ctx"}], title="r")

    before_reports = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id))).scalar_one()
    before_diffs = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id))).scalar_one()
    before_exports = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id))).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    export = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-reports/{report_id}/export",
        headers=headers,
    )
    assert export.status_code == 200

    after_reports = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticReport.id))).scalar_one()
    after_diffs = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticDiffReport.id))).scalar_one()
    after_exports = db_session.execute(select(func.count(AISystemGovernancePresetAssignmentDiagnosticExport.id))).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_reports == before_reports
    assert after_diffs == before_diffs
    assert after_exports == before_exports + 1
    assert after_audit >= before_audit + 1
