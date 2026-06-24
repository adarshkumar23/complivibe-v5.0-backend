import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_report import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_report import (
    AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_report import (
    AISystemGovernanceDiagnosticExportDiffGatingReport,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_phase526 import (
    _insert_diag_export_diff_gating_report,
    _make_export_diff_report,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525 import _create_profile

PRESET_BASE = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-presets"
)
EVAL_ENDPOINT_TMPL = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/evaluate-preset"
)
PRESET_REPORT_BASE = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports"
)
PRESET_SUMMARY_ENDPOINT = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-summary"
)


def _create_compare_report(
    db_session,
    *,
    organization_id: str,
    base_gating_report_id: str,
    compare_gating_report_id: str,
    max_severity_drift: str,
    review_required_drift: str,
    added_reason_codes: list[str],
    removed_reason_codes: list[str],
    changed_reason_codes: list[dict],
    reason_code_changes_count: int,
    severity_changes_count: int,
    status: str = "generated",
) -> str:
    row = AISystemGovernanceDiagnosticExportDiffGatingCompareReport(
        organization_id=uuid.UUID(organization_id),
        base_gating_report_id=uuid.UUID(base_gating_report_id),
        compare_gating_report_id=uuid.UUID(compare_gating_report_id),
        status=status,
        result_json={
            "added_reason_codes": added_reason_codes,
            "removed_reason_codes": removed_reason_codes,
            "changed_reason_codes": changed_reason_codes,
        },
        max_severity_drift=max_severity_drift,
        review_required_drift=review_required_drift,
        reason_code_changes_count=reason_code_changes_count,
        severity_changes_count=severity_changes_count,
    )
    db_session.add(row)
    db_session.flush()
    return str(row.id)


def _create_preset(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "name": "Diag Export Diff Compare Preset",
        "default_interpretation_band": "stable",
        "interpretation_rules_json": {},
        "status": "active",
    }
    payload.update(overrides)
    response = client.post(PRESET_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase527_preset_crud_and_validation(client, db_session):
    org, headers, _ = _make_export_diff_report(client, db_session, email_prefix="p527-crud")

    invalid_band = client.post(
        PRESET_BASE,
        headers=headers,
        json={
            "name": "invalid",
            "default_interpretation_band": "urgent",
            "interpretation_rules_json": {},
        },
    )
    assert invalid_band.status_code == 422

    invalid_watched = client.post(
        PRESET_BASE,
        headers=headers,
        json={
            "name": "invalid watched",
            "default_interpretation_band": "stable",
            "watched_reason_codes_json": ["NOT_A_REAL_EXPORT_DIFF_CODE"],
            "interpretation_rules_json": {},
        },
    )
    assert invalid_watched.status_code == 400

    invalid_ignored = client.post(
        PRESET_BASE,
        headers=headers,
        json={
            "name": "invalid ignored",
            "default_interpretation_band": "stable",
            "ignored_reason_codes_json": ["NOT_A_REAL_EXPORT_DIFF_CODE"],
            "interpretation_rules_json": {},
        },
    )
    assert invalid_ignored.status_code == 400

    preset = _create_preset(
        client,
        headers,
        interpretation_rules_json={
            "severity_increase_band": "review_required",
            "reason_code_changes_thresholds": [{"min_changes": 5, "band": "review_required"}, {"min_changes": 1, "band": "attention"}],
            "severity_changes_thresholds": [{"min_changes": 1, "band": "review_required"}],
        },
    )

    listing = client.get(PRESET_BASE, headers=headers)
    assert listing.status_code == 200
    assert any(item["id"] == preset["id"] for item in listing.json())

    updated = client.patch(
        f"{PRESET_BASE}/{preset['id']}",
        headers=headers,
        json={"status": "inactive", "default_interpretation_band": "attention"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"

    archive = client.post(
        f"{PRESET_BASE}/{preset['id']}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    blocked_update = client.patch(
        f"{PRESET_BASE}/{preset['id']}",
        headers=headers,
        json={"description": "should fail"},
    )
    assert blocked_update.status_code == 400

    other = bootstrap_org_user(client, email_prefix="p527-crud-other")
    cross_list = client.get(PRESET_BASE, headers=other["org_headers"])
    assert cross_list.status_code == 200
    assert all(item["organization_id"] == str(other["organization_id"]) for item in cross_list.json())


def test_phase527_evaluate_rules_persist_and_non_mutation(client, db_session):
    org, headers, export_diff_report_id = _make_export_diff_report(client, db_session, email_prefix="p527-eval")
    profile = _create_profile(client, headers)

    base_gating_report_id = _insert_diag_export_diff_gating_report(
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
    compare_gating_report_id = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[
            {
                "reason_code": "EXPORT_PAYLOAD_HASH_CHANGED",
                "count": 1,
                "severity": "high",
                "review_required": True,
            }
        ],
    )

    compare_report_id = _create_compare_report(
        db_session,
        organization_id=org["organization_id"],
        base_gating_report_id=base_gating_report_id,
        compare_gating_report_id=compare_gating_report_id,
        max_severity_drift="increased",
        review_required_drift="became_not_required",
        added_reason_codes=["EXPORT_PATH_CHANGED", "EXPORT_SOURCE_REPORT_CHANGED"],
        removed_reason_codes=["EXPORT_PATH_REMOVED"],
        changed_reason_codes=[
            {"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "change_type": "severity_changed", "before": "low", "after": "high"},
            {"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "change_type": "count_changed", "before": 1, "after": 3},
            {"reason_code": "EXPORT_PATH_CHANGED", "change_type": "review_required_changed", "before": False, "after": True},
        ],
        reason_code_changes_count=6,
        severity_changes_count=2,
    )

    preset = _create_preset(
        client,
        headers,
        watched_reason_codes_json=["EXPORT_PATH_CHANGED"],
        ignored_reason_codes_json=["EXPORT_PATH_CHANGED"],
        interpretation_rules_json={
            "severity_increase_band": "review_required",
            "severity_decrease_band": "attention",
            "review_required_flip_to_required_band": "critical_review",
            "review_required_flip_to_not_required_band": "attention",
            "watched_reason_code_band": "critical_review",
            "ignored_reason_codes_do_not_affect_band": True,
            "reason_code_changes_thresholds": [
                {"min_changes": 1, "band": "attention"},
                {"min_changes": 5, "band": "review_required"},
                {"min_changes": 10, "band": "critical_review"},
            ],
            "severity_changes_thresholds": [
                {"min_changes": 1, "band": "review_required"},
                {"min_changes": 3, "band": "critical_review"},
            ],
        },
    )

    compare_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == uuid.UUID(compare_report_id)
        )
    ).scalar_one()
    base_gating_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(base_gating_report_id)
        )
    ).scalar_one()
    compare_gating_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(compare_gating_report_id)
        )
    ).scalar_one()

    before_reports = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id))
    ).scalar_one()
    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    preview = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"], "persist_report": False},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["persisted"] is False
    assert body["preset_report_id"] is None
    assert body["interpretation_band"] == "review_required"
    assert body["review_required"] is True
    assert any(item["rule"] == "severity_increase_band" for item in body["matched_rules"])
    assert any(item["rule"] == "severity_changes_threshold" for item in body["matched_rules"])
    assert not any(item["rule"] == "watched_reason_code_band" for item in body["matched_rules"])

    after_reports = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id))
    ).scalar_one()
    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_reports == before_reports
    assert after_audit == before_audit

    # Explicitly allow watched reason code to override ignored suppression.
    update_override = client.patch(
        f"{PRESET_BASE}/{preset['id']}",
        headers=headers,
        json={
            "interpretation_rules_json": {
                "severity_increase_band": "review_required",
                "review_required_flip_to_not_required_band": "attention",
                "watched_reason_code_band": "critical_review",
                "ignored_reason_codes_do_not_affect_band": True,
                "watched_reason_codes_override_ignored": True,
            }
        },
    )
    assert update_override.status_code == 200

    persisted = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"], "persist_report": True},
    )
    assert persisted.status_code == 200
    pbody = persisted.json()
    assert pbody["persisted"] is True
    assert pbody["preset_report_id"] is not None
    assert pbody["interpretation_band"] == "critical_review"
    assert pbody["review_required"] is True
    assert any(item["rule"] == "watched_reason_code_band" for item in pbody["matched_rules"])

    compare_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == uuid.UUID(compare_report_id)
        )
    ).scalar_one()
    base_gating_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(base_gating_report_id)
        )
    ).scalar_one()
    compare_gating_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(compare_gating_report_id)
        )
    ).scalar_one()
    assert compare_after.updated_at == compare_before.updated_at
    assert base_gating_after.updated_at == base_gating_before.updated_at
    assert compare_gating_after.updated_at == compare_gating_before.updated_at


def test_phase527_preset_report_tenant_scope_archive_summary_and_audit(client, db_session):
    org1, h1, export_diff_1 = _make_export_diff_report(client, db_session, email_prefix="p527-t1")
    org2, h2, export_diff_2 = _make_export_diff_report(client, db_session, email_prefix="p527-t2")

    profile1 = _create_profile(client, h1)
    profile2 = _create_profile(client, h2)

    base1 = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        export_diff_report_id=export_diff_1,
        profile_id=profile1["id"],
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "EXPORT_PATH_UNCHANGED", "count": 1, "severity": "low", "review_required": False}],
    )
    cmp1 = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        export_diff_report_id=export_diff_1,
        profile_id=profile1["id"],
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "count": 1, "severity": "high", "review_required": True}],
    )
    compare1 = _create_compare_report(
        db_session,
        organization_id=org1["organization_id"],
        base_gating_report_id=base1,
        compare_gating_report_id=cmp1,
        max_severity_drift="decreased",
        review_required_drift="unchanged",
        added_reason_codes=[],
        removed_reason_codes=[],
        changed_reason_codes=[],
        reason_code_changes_count=0,
        severity_changes_count=0,
        status="archived",  # archived source compare report should still be evaluable
    )

    base2 = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org2["organization_id"],
        export_diff_report_id=export_diff_2,
        profile_id=profile2["id"],
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "EXPORT_PATH_UNCHANGED", "count": 1, "severity": "low", "review_required": False}],
    )
    cmp2 = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org2["organization_id"],
        export_diff_report_id=export_diff_2,
        profile_id=profile2["id"],
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "count": 1, "severity": "high", "review_required": True}],
    )
    compare2 = _create_compare_report(
        db_session,
        organization_id=org2["organization_id"],
        base_gating_report_id=base2,
        compare_gating_report_id=cmp2,
        max_severity_drift="increased",
        review_required_drift="became_required",
        added_reason_codes=["EXPORT_PAYLOAD_HASH_CHANGED"],
        removed_reason_codes=[],
        changed_reason_codes=[],
        reason_code_changes_count=1,
        severity_changes_count=0,
    )

    preset1 = _create_preset(client, h1, interpretation_rules_json={"severity_decrease_band": "attention"})
    preset2 = _create_preset(client, h2)
    preset1_update = client.patch(
        f"{PRESET_BASE}/{preset1['id']}",
        headers=h1,
        json={"description": "updated"},
    )
    assert preset1_update.status_code == 200

    cross_compare = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare2),
        headers=h1,
        json={"preset_id": preset1["id"], "persist_report": False},
    )
    assert cross_compare.status_code == 404

    cross_preset = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare1),
        headers=h1,
        json={"preset_id": preset2["id"], "persist_report": False},
    )
    assert cross_preset.status_code == 404

    persisted = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare1),
        headers=h1,
        json={"preset_id": preset1["id"], "persist_report": True},
    )
    assert persisted.status_code == 200
    preset_report_id = persisted.json()["preset_report_id"]
    assert persisted.json()["interpretation_band"] == "attention"

    reports_list = client.get(PRESET_REPORT_BASE, headers=h1)
    assert reports_list.status_code == 200
    assert any(item["id"] == preset_report_id for item in reports_list.json())

    cross_detail = client.get(f"{PRESET_REPORT_BASE}/{preset_report_id}", headers=h2)
    assert cross_detail.status_code == 404

    archive = client.post(
        f"{PRESET_REPORT_BASE}/{preset_report_id}/archive",
        headers=h1,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    summary = client.get(PRESET_SUMMARY_ENDPOINT, headers=h1)
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_preset_reports"] >= 1
    assert s["archived_preset_reports"] >= 1
    assert s["review_required_reports"] >= 0
    assert isinstance(s["by_interpretation_band"], dict)

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset.created" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset.updated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.generated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.archived" in actions
