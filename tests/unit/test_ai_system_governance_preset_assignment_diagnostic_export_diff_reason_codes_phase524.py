import uuid

from sqlalchemy import func, select

from app.models.ai_system_governance_preset_assignment_diagnostic_export import (
    AISystemGovernancePresetAssignmentDiagnosticExport,
)
from app.models.ai_system_governance_preset_assignment_diagnostic_export_diff_report import (
    AISystemGovernancePresetAssignmentDiagnosticExportDiffReport,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diffs_phase523 import (
    _export_report,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_reports_phase521 import (
    _create_assignment,
    _persist_coverage_report,
)
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_assignments_phase519 import _create_context
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset


REASON_CODES_ENDPOINT = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-reason-codes"
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


def test_phase524_export_diff_reason_code_catalog_deterministic(client):
    org = bootstrap_org_user(client, email_prefix="p524-catalog")
    headers = org["org_headers"]

    first = client.get(REASON_CODES_ENDPOINT, headers=headers)
    second = client.get(REASON_CODES_ENDPOINT, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    codes = [row["code"] for row in first.json()["reason_codes"]]
    assert codes == sorted(codes)
    assert "EXPORT_PATH_ADDED" in codes
    assert "EXPORT_PAYLOAD_HASH_CHANGED" in codes
    assert "SOURCE_EXPORT_REVOKED" in codes


def test_phase524_export_diff_reason_codes_in_response_and_no_audit_when_not_persisted(client, db_session):
    _, headers = _bootstrap_with_global_assignment(client, db_session, email_prefix="p524-diff")

    report_base = _persist_coverage_report(
        client,
        headers,
        contexts=[{"context_key": "a"}],
        title="base",
    )
    report_compare = _persist_coverage_report(
        client,
        headers,
        contexts=[{"context_key": "a"}, {"context_key": "b"}],
        title="compare",
    )
    export_base = _export_report(client, headers, report_base)
    export_compare = _export_report(client, headers, report_compare)

    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    response = client.post(
        DIFF_ENDPOINT,
        headers=headers,
        json={
            "base_export_id": export_base["export_id"],
            "compare_export_id": export_compare["export_id"],
            "persist_diff": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reason_code_count"] > 0
    assert body["reason_code_summary"]["EXPORT_PAYLOAD_HASH_CHANGED"] >= 1
    assert body["reason_code_summary"]["EXPORT_PATH_ADDED"] >= 1
    assert body["reason_code_summary"]["EXPORT_PATH_CHANGED"] >= 1
    assert body["reason_code_summary"]["EXPORT_TYPE_MATCHED"] >= 1
    assert body["reason_code_summary"]["EXPORT_PATH_UNCHANGED"] >= 1
    assert all("reason_code" in row and "severity_hint" in row for row in body["path_diffs"])

    reverse = client.post(
        DIFF_ENDPOINT,
        headers=headers,
        json={
            "base_export_id": export_compare["export_id"],
            "compare_export_id": export_base["export_id"],
            "persist_diff": False,
        },
    )
    assert reverse.status_code == 200
    reverse_body = reverse.json()
    assert reverse_body["reason_code_summary"]["EXPORT_PATH_REMOVED"] >= 1

    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_audit == before_audit


def test_phase524_export_diff_reason_codes_for_revoked_and_invalid_signature(client, db_session):
    _, headers = _bootstrap_with_global_assignment(client, db_session, email_prefix="p524-revoke")

    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "b"}], title="b")
    export_a = _export_report(client, headers, report_a)
    export_b = _export_report(client, headers, report_b)

    revoke = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_b['export_id']}/revoke",
        headers=headers,
        json={"reason": "revoke compare"},
    )
    assert revoke.status_code == 200

    base_row = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExport).where(
            AISystemGovernancePresetAssignmentDiagnosticExport.id == uuid.UUID(export_a["export_id"])
        )
    ).scalar_one()
    base_row.internal_signature = "tampered-signature"
    db_session.commit()

    response = client.post(
        DIFF_ENDPOINT,
        headers=headers,
        json={
            "base_export_id": export_a["export_id"],
            "compare_export_id": export_b["export_id"],
            "persist_diff": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reason_code_summary"]["BASE_EXPORT_SIGNATURE_INVALID"] >= 1
    assert body["reason_code_summary"]["BASE_EXPORT_UNTRUSTED"] >= 1
    assert body["reason_code_summary"]["COMPARE_EXPORT_UNTRUSTED"] >= 1
    assert body["reason_code_summary"]["SOURCE_EXPORT_REVOKED"] >= 1


def test_phase524_export_diff_reason_codes_persist_detail_and_summary(client, db_session):
    _, headers = _bootstrap_with_global_assignment(client, db_session, email_prefix="p524-persist")

    report_a = _persist_coverage_report(client, headers, contexts=[{"context_key": "a"}], title="a")
    report_b = _persist_coverage_report(client, headers, contexts=[{"context_key": "a", "rollout_class": "x"}], title="b")
    export_a = _export_report(client, headers, report_a)
    export_b = _export_report(client, headers, report_b)

    response = client.post(
        DIFF_ENDPOINT,
        headers=headers,
        json={
            "base_export_id": export_a["export_id"],
            "compare_export_id": export_b["export_id"],
            "persist_diff": True,
            "title": "phase524",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["export_diff_report_id"] is not None
    assert body["reason_code_count"] > 0

    row = db_session.execute(
        select(AISystemGovernancePresetAssignmentDiagnosticExportDiffReport).where(
            AISystemGovernancePresetAssignmentDiagnosticExportDiffReport.id == uuid.UUID(body["export_diff_report_id"])
        )
    ).scalar_one()
    assert isinstance(row.reason_code_summary_json, dict)
    assert row.reason_code_count == body["reason_code_count"]

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{body['export_diff_report_id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["reason_code_count"] == body["reason_code_count"]
    assert detail_body["reason_code_summary_json"] == body["reason_code_summary"]

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_reason_code_occurrences"] >= body["reason_code_count"]
    assert isinstance(summary_body["top_reason_codes"], list)
    assert summary_body["top_reason_codes"]

    top = summary_body["top_reason_codes"]
    for i in range(len(top) - 1):
        prev = top[i]
        cur = top[i + 1]
        assert prev["count"] > cur["count"] or (
            prev["count"] == cur["count"] and prev["reason_code"] <= cur["reason_code"]
        )
