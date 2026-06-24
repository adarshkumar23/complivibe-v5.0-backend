import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_report import (
    AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_report import (
    AISystemGovernanceDiagnosticExportDiffGatingReport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
)
from app.models.audit_log import AuditLog
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525 import (
    _bootstrap_with_global_assignment,
    _create_profile,
    _persist_export_diff,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diffs_phase523 import _export_report
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_reports_phase521 import _persist_coverage_report

COMPARE_ENDPOINT = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/compare"
)
COMPARE_REPORT_BASE = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports"
)
COMPARE_SUMMARY_ENDPOINT = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-summary"
)


def _make_export_diff_report(client, db_session, *, email_prefix: str) -> tuple[dict, dict[str, str], str]:
    org, headers = _bootstrap_with_global_assignment(client, db_session, email_prefix=email_prefix)
    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}, {"context_key": "b"}], title="b")
    export_a = _export_report(client, headers, report_a)
    export_b = _export_report(client, headers, report_b)
    export_diff_report_id = _persist_export_diff(client, headers, export_a["export_id"], export_b["export_id"])
    return org, headers, export_diff_report_id


def _insert_diag_export_diff_gating_report(
    db_session,
    *,
    organization_id: str,
    export_diff_report_id: str,
    profile_id: str,
    max_severity: str,
    review_required: bool,
    reason_code_count: int,
    reason_code_classifications: list[dict],
    severity_summary: dict[str, int] | None = None,
    status: str = "generated",
) -> str:
    row = AISystemGovernanceDiagnosticExportDiffGatingReport(
        organization_id=uuid.UUID(organization_id),
        export_diff_report_id=uuid.UUID(export_diff_report_id),
        gating_profile_id=uuid.UUID(profile_id),
        status=status,
        result_json={
            "reason_code_classifications": reason_code_classifications,
            "severity_summary": severity_summary
            or {"info": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
        },
        max_severity=max_severity,
        review_required=review_required,
        reason_code_count=reason_code_count,
    )
    db_session.add(row)
    db_session.flush()
    return str(row.id)


def test_phase526_compare_preview_read_only_and_reason_code_drift(client, db_session):
    org, headers, export_diff_report_id = _make_export_diff_report(client, db_session, email_prefix="p526-preview")
    profile = _create_profile(client, headers)

    base_gating_report_id = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="low",
        review_required=False,
        reason_code_count=3,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PATH_CHANGED", "count": 1, "severity": "low", "review_required": False},
            {
                "reason_code": "EXPORT_PAYLOAD_HASH_CHANGED",
                "count": 2,
                "severity": "medium",
                "review_required": False,
            },
        ],
    )
    compare_gating_report_id = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="critical",
        review_required=True,
        reason_code_count=5,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PATH_CHANGED", "count": 4, "severity": "high", "review_required": True},
            {
                "reason_code": "EXPORT_SOURCE_REPORT_CHANGED",
                "count": 1,
                "severity": "low",
                "review_required": False,
            },
        ],
    )

    base_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(base_gating_report_id)
        )
    ).scalar_one()
    compare_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(compare_gating_report_id)
        )
    ).scalar_one()
    export_diff_before = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(export_diff_report_id)
        )
    ).scalar_one()

    before_compare_reports = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id))
    ).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    preview = client.post(
        COMPARE_ENDPOINT,
        headers=headers,
        json={
            "base_gating_report_id": base_gating_report_id,
            "compare_gating_report_id": compare_gating_report_id,
            "persist_compare": False,
        },
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["persisted"] is False
    assert body["compare_report_id"] is None
    assert body["max_severity_drift"] == "increased"
    assert body["review_required_drift"] == "became_required"
    assert set(body["added_reason_codes"]) == {"EXPORT_SOURCE_REPORT_CHANGED"}
    assert set(body["removed_reason_codes"]) == {"EXPORT_PAYLOAD_HASH_CHANGED"}

    change_map = {(item["reason_code"], item["change_type"]) for item in body["changed_reason_codes"]}
    assert ("EXPORT_PATH_CHANGED", "severity_changed") in change_map
    assert ("EXPORT_PATH_CHANGED", "review_required_changed") in change_map
    assert ("EXPORT_PATH_CHANGED", "count_changed") in change_map
    assert body["reason_code_changes_count"] == 5
    assert body["severity_changes_count"] == 1

    list_reports = client.get(COMPARE_REPORT_BASE, headers=headers)
    assert list_reports.status_code == 200
    assert list_reports.json() == []

    after_compare_reports = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id))
    ).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_compare_reports == before_compare_reports
    assert after_audit == before_audit

    base_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(base_gating_report_id)
        )
    ).scalar_one()
    compare_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(compare_gating_report_id)
        )
    ).scalar_one()
    export_diff_after = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(export_diff_report_id)
        )
    ).scalar_one()
    assert base_after.updated_at == base_before.updated_at
    assert compare_after.updated_at == compare_before.updated_at
    assert export_diff_after.updated_at == export_diff_before.updated_at


def test_phase526_compare_persist_archive_summary_and_archived_source(client, db_session):
    org, headers, export_diff_report_id = _make_export_diff_report(client, db_session, email_prefix="p526-persist")
    profile = _create_profile(client, headers)

    high = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="critical",
        review_required=True,
        reason_code_count=4,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "count": 4, "severity": "critical", "review_required": True}
        ],
    )
    low = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PATH_UNCHANGED", "count": 1, "severity": "low", "review_required": False}
        ],
    )
    same = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PATH_UNCHANGED", "count": 1, "severity": "low", "review_required": False}
        ],
    )

    persisted = client.post(
        COMPARE_ENDPOINT,
        headers=headers,
        json={
            "base_gating_report_id": high,
            "compare_gating_report_id": low,
            "persist_compare": True,
            "title": "baseline",
        },
    )
    assert persisted.status_code == 200
    persisted_body = persisted.json()
    assert persisted_body["persisted"] is True
    assert persisted_body["compare_report_id"] is not None
    assert persisted_body["max_severity_drift"] == "decreased"
    assert persisted_body["review_required_drift"] == "became_not_required"

    unchanged = client.post(
        COMPARE_ENDPOINT,
        headers=headers,
        json={
            "base_gating_report_id": low,
            "compare_gating_report_id": same,
            "persist_compare": False,
        },
    )
    assert unchanged.status_code == 200
    assert unchanged.json()["max_severity_drift"] == "unchanged"
    assert unchanged.json()["review_required_drift"] == "unchanged"

    # Archived source gating reports can still be compared.
    archived_source = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-reports/{high}/archive",
        headers=headers,
        json={"reason": "archive source"},
    )
    assert archived_source.status_code == 200
    compare_archived_source = client.post(
        COMPARE_ENDPOINT,
        headers=headers,
        json={
            "base_gating_report_id": high,
            "compare_gating_report_id": low,
            "persist_compare": False,
        },
    )
    assert compare_archived_source.status_code == 200

    list_reports = client.get(
        f"{COMPARE_REPORT_BASE}?max_severity_drift=decreased&review_required_drift=became_not_required",
        headers=headers,
    )
    assert list_reports.status_code == 200
    assert any(item["id"] == persisted_body["compare_report_id"] for item in list_reports.json())

    detail = client.get(f"{COMPARE_REPORT_BASE}/{persisted_body['compare_report_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == persisted_body["compare_report_id"]

    archived = client.post(
        f"{COMPARE_REPORT_BASE}/{persisted_body['compare_report_id']}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary = client.get(COMPARE_SUMMARY_ENDPOINT, headers=headers)
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_compare_reports"] >= 1
    assert s["active_compare_reports"] >= 0
    assert s["archived_compare_reports"] >= 1
    assert s["severity_decreased_reports"] >= 1
    assert s["severity_unchanged_reports"] >= 0
    assert s["review_required_became_not_required_reports"] >= 1
    assert s["review_required_unchanged_reports"] >= 0
    assert s["total_reason_code_changes"] >= 0
    assert s["total_severity_changes"] >= 0

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_report.generated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_report.archived" in actions


def test_phase526_compare_tenant_isolation_for_base_and_compare(client, db_session):
    org1, h1, export_diff_id_1 = _make_export_diff_report(client, db_session, email_prefix="p526-t1")
    org2, h2, export_diff_id_2 = _make_export_diff_report(client, db_session, email_prefix="p526-t2")

    profile1 = _create_profile(client, h1)
    profile2 = _create_profile(client, h2)

    r1 = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        export_diff_report_id=export_diff_id_1,
        profile_id=profile1["id"],
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PATH_CHANGED", "count": 1, "severity": "low", "review_required": False}
        ],
    )
    r2 = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        export_diff_report_id=export_diff_id_1,
        profile_id=profile1["id"],
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "count": 1, "severity": "high", "review_required": True}
        ],
    )
    other = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org2["organization_id"],
        export_diff_report_id=export_diff_id_2,
        profile_id=profile2["id"],
        max_severity="medium",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[
            {
                "reason_code": "EXPORT_SOURCE_REPORT_CHANGED",
                "count": 1,
                "severity": "medium",
                "review_required": False,
            }
        ],
    )

    bad_base = client.post(
        COMPARE_ENDPOINT,
        headers=h1,
        json={"base_gating_report_id": other, "compare_gating_report_id": r2},
    )
    assert bad_base.status_code == 404

    bad_compare = client.post(
        COMPARE_ENDPOINT,
        headers=h1,
        json={"base_gating_report_id": r1, "compare_gating_report_id": other},
    )
    assert bad_compare.status_code == 404

    ok = client.post(
        COMPARE_ENDPOINT,
        headers=h1,
        json={"base_gating_report_id": r1, "compare_gating_report_id": r2, "persist_compare": True},
    )
    assert ok.status_code == 200
    compare_report_id = ok.json()["compare_report_id"]

    cross_detail = client.get(f"{COMPARE_REPORT_BASE}/{compare_report_id}", headers=h2)
    assert cross_detail.status_code == 404

    list_h1 = client.get(COMPARE_REPORT_BASE, headers=h1)
    list_h2 = client.get(COMPARE_REPORT_BASE, headers=h2)
    assert list_h1.status_code == 200
    assert list_h2.status_code == 200
    ids1 = {item["id"] for item in list_h1.json()}
    ids2 = {item["id"] for item in list_h2.json()}
    assert compare_report_id in ids1
    assert compare_report_id not in ids2
