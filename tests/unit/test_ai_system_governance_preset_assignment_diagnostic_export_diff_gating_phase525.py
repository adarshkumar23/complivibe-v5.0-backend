import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_diagnostic_export_diff_gating_profile import (
    AISystemGovernanceDiagnosticExportDiffGatingProfile,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_report import (
    AISystemGovernanceDiagnosticExportDiffGatingReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export import (
    AISystemGovernancePresetAssignmentDiagnosticExport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diffs_phase523 import _export_report
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_reports_phase521 import (
    _create_assignment,
    _persist_coverage_report,
)
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519 import _create_context
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset


PROFILE_BASE = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-profiles"
)
REPORT_BASE = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports"
)
DIFF_ENDPOINT = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-exports/diff"
)


def _bootstrap_with_global_assignment(client, db_session, email_prefix: str):
    org = bootstrap_org_user(client, email_prefix=email_prefix)
    headers = org["org_headers"]
    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    _create_assignment(client, headers, {"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": "global"})
    return org, headers


def _persist_export_diff(client, headers: dict[str, str], base_export_id: str, compare_export_id: str) -> str:
    response = client.post(
        DIFF_ENDPOINT,
        headers=headers,
        json={
            "base_export_id": base_export_id,
            "compare_export_id": compare_export_id,
            "persist_diff": True,
        },
    )
    assert response.status_code == 200
    return response.json()["export_diff_report_id"]


def _create_profile(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "name": "Export Diff Gating",
        "default_severity": "medium",
        "review_required_threshold": "high",
        "reason_code_rules_json": {},
        "status": "active",
    }
    payload.update(overrides)
    response = client.post(PROFILE_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase525_profile_crud_and_validation(client, db_session):
    org, headers = _bootstrap_with_global_assignment(client, db_session, email_prefix="p525-profile")

    invalid = client.post(
        PROFILE_BASE,
        headers=headers,
        json={
            "name": "bad",
            "default_severity": "urgent",
            "review_required_threshold": "high",
            "reason_code_rules_json": {},
        },
    )
    assert invalid.status_code == 422

    invalid_threshold = client.post(
        PROFILE_BASE,
        headers=headers,
        json={
            "name": "bad-threshold",
            "default_severity": "info",
            "review_required_threshold": "urgent",
            "reason_code_rules_json": {},
        },
    )
    assert invalid_threshold.status_code == 422

    unknown_code = client.post(
        PROFILE_BASE,
        headers=headers,
        json={
            "name": "unknown-code",
            "default_severity": "low",
            "review_required_threshold": "high",
            "reason_code_rules_json": {"NOT_A_REAL_EXPORT_DIFF_CODE": {"severity": "high"}},
        },
    )
    assert unknown_code.status_code == 400

    profile = _create_profile(
        client,
        headers,
        reason_code_rules_json={
            "EXPORT_PAYLOAD_HASH_CHANGED": {"severity": "critical", "review_required": True},
        },
    )

    listing = client.get(PROFILE_BASE, headers=headers)
    assert listing.status_code == 200
    assert any(row["id"] == profile["id"] for row in listing.json())

    other = bootstrap_org_user(client, email_prefix="p525-profile-other")
    cross = client.get(PROFILE_BASE, headers=other["org_headers"])
    assert cross.status_code == 200
    assert all(row["organization_id"] == str(other["organization_id"]) for row in cross.json())

    updated = client.patch(
        f"{PROFILE_BASE}/{profile['id']}",
        headers=headers,
        json={"default_severity": "low", "review_required_threshold": "medium"},
    )
    assert updated.status_code == 200
    assert updated.json()["default_severity"] == "low"

    archived = client.post(
        f"{PROFILE_BASE}/{profile['id']}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    blocked_update = client.patch(
        f"{PROFILE_BASE}/{profile['id']}",
        headers=headers,
        json={"description": "should fail"},
    )
    assert blocked_update.status_code == 400


def test_phase525_classify_non_persist_persist_and_mutation_guards(client, db_session):
    _, headers = _bootstrap_with_global_assignment(client, db_session, email_prefix="p525-classify")

    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}, {"context_key": "b"}], title="b")
    export_a = _export_report(client, headers, report_a)
    export_b = _export_report(client, headers, report_b)
    export_diff_report_id = _persist_export_diff(client, headers, export_a["export_id"], export_b["export_id"])

    profile = _create_profile(
        client,
        headers,
        default_severity="low",
        review_required_threshold="critical",
        reason_code_rules_json={"EXPORT_PAYLOAD_HASH_CHANGED": {"severity": "high", "review_required": True}},
    )

    source_diff_before = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(export_diff_report_id)
        )
    ).scalar_one()
    source_diff_before_updated = source_diff_before.updated_at
    source_diff_before_reason_count = source_diff_before.reason_code_count

    exports_before = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExport)
        .where(
            AISystemGovernancePresetAssignmentDiagnosticExport.id.in_(
                [uuid.UUID(export_a["export_id"]), uuid.UUID(export_b["export_id"])]
            )
        )
        .order_by(AISystemGovernancePresetAssignmentDiagnosticExport.id.asc())
    ).scalars().all()
    export_before_map = {str(row.id): (row.status, row.updated_at) for row in exports_before}

    before_reports = db_session.execute(select(func.count(AISystemGovernanceDiagnosticExportDiffGatingReport.id))).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    preview = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/classify",
        headers=headers,
        json={"gating_profile_id": profile["id"], "persist_report": False},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["persisted"] is False
    assert preview_body["gating_report_id"] is None
    assert preview_body["max_severity"] == "high"
    assert preview_body["review_required"] is True

    after_reports = db_session.execute(select(func.count(AISystemGovernanceDiagnosticExportDiffGatingReport.id))).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_reports == before_reports
    assert after_audit == before_audit

    persisted = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/classify",
        headers=headers,
        json={"gating_profile_id": profile["id"], "persist_report": True},
    )
    assert persisted.status_code == 200
    body = persisted.json()
    assert body["persisted"] is True
    assert body["gating_report_id"] is not None

    source_diff_after = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(export_diff_report_id)
        )
    ).scalar_one()
    assert source_diff_after.reason_code_count == source_diff_before_reason_count
    assert source_diff_after.updated_at == source_diff_before_updated

    exports_after = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExport)
        .where(
            AISystemGovernancePresetAssignmentDiagnosticExport.id.in_(
                [uuid.UUID(export_a["export_id"]), uuid.UUID(export_b["export_id"])]
            )
        )
        .order_by(AISystemGovernancePresetAssignmentDiagnosticExport.id.asc())
    ).scalars().all()
    export_after_map = {str(row.id): (row.status, row.updated_at) for row in exports_after}
    assert export_after_map == export_before_map


def test_phase525_classification_defaults_tenant_scope_archive_and_summary(client, db_session):
    org1, h1 = _bootstrap_with_global_assignment(client, db_session, email_prefix="p525-t1")
    org2, h2 = _bootstrap_with_global_assignment(client, db_session, email_prefix="p525-t2")

    r1a = _persist_coverage_report(client, h1, contexts=[{"context_key": "a"}], title="r1a")
    r1b = _persist_coverage_report(client, h1, contexts=[{"context_key": "a", "rollout_class": "x"}], title="r1b")
    e1a = _export_report(client, h1, r1a)
    e1b = _export_report(client, h1, r1b)
    export_diff_id = _persist_export_diff(client, h1, e1a["export_id"], e1b["export_id"])

    r2a = _persist_coverage_report(client, h2, contexts=[{"context_key": "a"}], title="r2a")
    r2b = _persist_coverage_report(client, h2, contexts=[{"context_key": "b"}], title="r2b")
    e2a = _export_report(client, h2, r2a)
    e2b = _export_report(client, h2, r2b)
    other_diff_id = _persist_export_diff(client, h2, e2a["export_id"], e2b["export_id"])

    profile = _create_profile(client, h1, default_severity="medium", review_required_threshold="high")
    profile_update = client.patch(
        f"{PROFILE_BASE}/{profile['id']}",
        headers=h1,
        json={"description": "updated"},
    )
    assert profile_update.status_code == 200

    # No reason-code path => info / review_required false
    row = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(export_diff_id)
        )
    ).scalar_one()
    row.reason_code_summary_json = {}
    row.reason_code_count = 0
    row.diff_json = {"path_diffs": []}
    db_session.commit()

    classify_none = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": profile["id"], "persist_report": False},
    )
    assert classify_none.status_code == 200
    cnone = classify_none.json()
    assert cnone["max_severity"] == "info"
    assert cnone["review_required"] is False

    # default severity for unmapped code
    row = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(export_diff_id)
        )
    ).scalar_one()
    row.reason_code_summary_json = {"EXPORT_SOURCE_REPORT_CHANGED": 1}
    row.reason_code_count = 1
    db_session.commit()

    classify_default = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": profile["id"], "persist_report": False},
    )
    assert classify_default.status_code == 200
    cdef = classify_default.json()
    by_code = {item["reason_code"]: item for item in cdef["reason_code_classifications"]}
    assert by_code["EXPORT_SOURCE_REPORT_CHANGED"]["severity"] == "medium"
    assert cdef["max_severity"] == "medium"
    assert cdef["review_required"] is False

    # threshold rule
    classify_threshold = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": profile["id"], "persist_report": True},
    )
    assert classify_threshold.status_code == 200

    # explicit review_required rule
    explicit_profile = _create_profile(
        client,
        h1,
        default_severity="low",
        review_required_threshold="critical",
        reason_code_rules_json={"EXPORT_SOURCE_REPORT_CHANGED": {"severity": "low", "review_required": True}},
    )
    classify_explicit = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": explicit_profile["id"], "persist_report": True},
    )
    assert classify_explicit.status_code == 200
    assert classify_explicit.json()["review_required"] is True

    cross_diff = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{other_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": profile["id"], "persist_report": False},
    )
    assert cross_diff.status_code == 404

    cross_profile = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h2,
        json={"gating_profile_id": profile["id"], "persist_report": False},
    )
    assert cross_profile.status_code == 404

    inactive = _create_profile(client, h1, status="inactive")
    inactive_try = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": inactive["id"], "persist_report": False},
    )
    assert inactive_try.status_code == 400
    archive_profile = client.post(
        f"{PROFILE_BASE}/{profile['id']}/archive",
        headers=h1,
        json={"reason": "done"},
    )
    assert archive_profile.status_code == 200

    report_list = client.get(REPORT_BASE, headers=h1)
    assert report_list.status_code == 200
    report_rows = report_list.json()
    assert report_rows

    detail_id = report_rows[0]["id"]
    cross_detail = client.get(f"{REPORT_BASE}/{detail_id}", headers=h2)
    assert cross_detail.status_code == 404

    archived = client.post(f"{REPORT_BASE}/{detail_id}/archive", headers=h1, json={"reason": "done"})
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-summary",
        headers=h1,
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_gating_reports"] >= 1
    assert s["archived_gating_reports"] >= 1
    assert isinstance(s["by_max_severity"], dict)

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_diagnostic_export_diff_gating_profile.created" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_profile.updated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_profile.archived" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_report.generated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_report.archived" in actions

    # persisted=false classify does not write audit
    before = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    no_persist = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_id}/classify",
        headers=h1,
        json={"gating_profile_id": explicit_profile["id"], "persist_report": False},
    )
    assert no_persist.status_code == 200
    after = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after == before
