from pathlib import Path

from sqlalchemy import func, select

from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory,
)
from app.models.audit_log import AuditLog
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_phase526 import (
    COMPARE_ENDPOINT,
    _insert_diag_export_diff_gating_report,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_assignments_phase529 import (
    ASSIGNMENT_BASE,
    EVAL_DEFAULT_TMPL,
    RESOLVE_ENDPOINT,
    _create_assignment,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_versions_phase528 import (
    _create_context,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_presets_phase527 import (
    EVAL_ENDPOINT_TMPL,
    _create_preset,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525 import (
    _create_profile,
    _persist_export_diff,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_reason_codes_phase524 import (
    REASON_CODES_ENDPOINT,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diffs_phase523 import _export_report
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_reports_phase521 import _persist_coverage_report

CONTRACTS_ENDPOINT = "/api/v1/ai-governance/contracts/phase5"
CONTRACTS_COMPAT_ENDPOINT = "/api/v1/ai-governance/contracts/phase5/compatibility-summary"

REQUIRED_GROUPS = {
    "ai_system_inventory",
    "governance_reviews",
    "governance_attestations",
    "review_scheduling",
    "recurrence_templates",
    "sequence_packs",
    "guardrail_freeze_windows",
    "guardrail_policy_sets",
    "guardrail_policy_assignments",
    "policy_resolution_simulations",
    "policy_resolution_diffs",
    "gating_profiles",
    "gating_compare_reports",
    "gating_compare_presets",
    "gating_compare_preset_versions",
    "gating_compare_preset_assignments",
    "preset_assignment_diagnostics",
    "diagnostic_reports",
    "diagnostic_exports",
    "diagnostic_export_diffs",
    "diagnostic_export_diff_reason_codes",
    "diagnostic_export_diff_gating",
    "diagnostic_export_diff_gating_compare",
    "diagnostic_export_diff_gating_compare_presets",
    "diagnostic_export_diff_gating_compare_preset_versions",
    "diagnostic_export_diff_gating_compare_preset_assignments",
}


def test_phase60_contract_registry_endpoints_and_required_groups(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p60-contracts")
    headers = org["org_headers"]

    before_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    before_assignments = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    before_assignment_history = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()

    listing = client.get(CONTRACTS_ENDPOINT, headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["phase"] == "phase5"
    assert body["status"] == "closed"
    assert body["group_count"] >= len(REQUIRED_GROUPS)
    assert "stability contracts" in body["caveat"].lower()

    keys = {group["group_key"] for group in body["groups"]}
    assert REQUIRED_GROUPS.issubset(keys)
    for group in body["groups"]:
        assert group["critical_endpoints"]
        assert group["response_contract_fields"]

    # Static route must resolve to compatibility summary, not dynamic group key route.
    compat = client.get(CONTRACTS_COMPAT_ENDPOINT, headers=headers)
    assert compat.status_code == 200
    compat_body = compat.json()
    assert compat_body["phase"] == "phase5"
    assert compat_body["status"] == "closed"
    assert compat_body["protected_groups_count"] >= len(REQUIRED_GROUPS)
    assert compat_body["protected_endpoint_count"] > 0

    detail = client.get("/api/v1/ai-governance/contracts/phase5/diagnostic_exports", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["group_key"] == "diagnostic_exports"

    unknown = client.get("/api/v1/ai-governance/contracts/phase5/not-a-group", headers=headers)
    assert unknown.status_code == 404

    # Auth + tenant-org header required.
    unauth = client.get(CONTRACTS_ENDPOINT)
    assert unauth.status_code in (400, 401)
    missing_org = client.get(CONTRACTS_ENDPOINT, headers=org["headers"])
    assert missing_org.status_code in (400, 401, 422)

    after_audit = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    after_assignments = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    after_assignment_history = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    assert after_audit == before_audit
    assert after_assignments == before_assignments
    assert after_assignment_history == before_assignment_history


def test_phase60_representative_phase5_response_shapes(client, db_session):
    _, headers, compare_report_id, compare_gating_report_id = _create_context(client, db_session, "p60-shapes")
    preset = _create_preset(client, headers, interpretation_rules_json={})
    assignment = _create_assignment(client, headers, preset_id=preset["id"], scope_type="all_ai_governance", priority=10)

    resolve_resp = client.post(
        RESOLVE_ENDPOINT,
        headers=headers,
        json={"compare_report_id": compare_report_id},
    )
    assert resolve_resp.status_code == 200
    resolve_body = resolve_resp.json()
    for key in ("resolved_preset_id", "resolution_source", "assignment_id", "precedence_trace", "caveat"):
        assert key in resolve_body
    assert resolve_body["resolved_preset_id"] == preset["id"]
    assert resolve_body["assignment_id"] == assignment["id"]

    coverage_resp = client.post(
        f"{ASSIGNMENT_BASE}/coverage-diagnostics",
        headers=headers,
        json={"contexts": [{"context_key": "ctx", "compare_report_id": compare_report_id}]},
    )
    assert coverage_resp.status_code == 200
    coverage_body = coverage_resp.json()
    for key in (
        "context_count",
        "resolved_contexts_count",
        "unresolved_contexts_count",
        "warning_contexts_count",
        "critical_contexts_count",
        "contexts",
        "aggregate_diagnostics",
        "caveat",
    ):
        assert key in coverage_body
    assert isinstance(coverage_body["contexts"], list)

    report_base = _persist_coverage_report(client, headers, contexts=[{"context_key": "base"}], title="base")
    report_compare = _persist_coverage_report(client, headers, contexts=[{"context_key": "base"}, {"context_key": "x"}], title="compare")
    export_base = _export_report(client, headers, report_base)
    export_compare = _export_report(client, headers, report_compare)

    verify_resp = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/{export_base['export_id']}/verify",
        headers=headers,
    )
    assert verify_resp.status_code == 200
    verify_body = verify_resp.json()
    for key in (
        "valid_hash",
        "valid_signature",
        "trusted",
        "canonical_payload_sha256",
        "recomputed_sha256",
        "signature_algorithm",
        "signing_key_id",
        "status",
        "caveat",
    ):
        assert key in verify_body

    diff_resp = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-exports/diff",
        headers=headers,
        json={
            "base_export_id": export_base["export_id"],
            "compare_export_id": export_compare["export_id"],
            "persist_diff": True,
        },
    )
    assert diff_resp.status_code == 200
    diff_body = diff_resp.json()
    for key in (
        "payload_hash_changed",
        "path_diffs",
        "reason_code_summary",
        "reason_code_count",
        "base_verification",
        "compare_verification",
        "caveat",
    ):
        assert key in diff_body
    export_diff_report_id = diff_body["export_diff_report_id"]

    catalog_resp = client.get(REASON_CODES_ENDPOINT, headers=headers)
    assert catalog_resp.status_code == 200
    catalog_body = catalog_resp.json()
    assert "reason_codes" in catalog_body
    assert isinstance(catalog_body["reason_codes"], list)

    profile = _create_profile(client, headers)
    classify_resp = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/diagnostic-export-diff-reports/{export_diff_report_id}/classify",
        headers=headers,
        json={"gating_profile_id": profile["id"], "persist_report": True},
    )
    assert classify_resp.status_code == 200
    classify_body = classify_resp.json()
    for key in (
        "max_severity",
        "review_required",
        "reason_code_count",
        "severity_summary",
        "reason_code_classifications",
        "caveat",
    ):
        assert key in classify_body
    gating_report_id = classify_body["gating_report_id"]

    compare_resp = client.post(
        COMPARE_ENDPOINT,
        headers=headers,
        json={
            "base_gating_report_id": compare_gating_report_id,
            "compare_gating_report_id": gating_report_id,
            "persist_compare": False,
        },
    )
    assert compare_resp.status_code == 200
    compare_body = compare_resp.json()
    for key in (
        "max_severity_drift",
        "review_required_drift",
        "reason_code_changes_count",
        "severity_changes_count",
        "added_reason_codes",
        "changed_reason_codes",
        "aggregate_delta",
        "caveat",
    ):
        assert key in compare_body

    compare_report = client.post(
        COMPARE_ENDPOINT,
        headers=headers,
        json={
            "base_gating_report_id": compare_gating_report_id,
            "compare_gating_report_id": gating_report_id,
            "persist_compare": True,
        },
    )
    assert compare_report.status_code == 200
    persisted_compare_id = compare_report.json()["compare_report_id"]

    eval_preset_resp = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=persisted_compare_id),
        headers=headers,
        json={"preset_id": preset["id"], "persist_report": False},
    )
    assert eval_preset_resp.status_code == 200
    eval_preset_body = eval_preset_resp.json()
    for key in (
        "preset_id",
        "preset_version_id",
        "preset_snapshot_used",
        "version_resolution_source",
        "pinned_version_id",
        "explicit_version_override_used",
        "version_override_reason",
        "interpretation_band",
        "review_required",
        "matched_rules",
        "caveat",
    ):
        assert key in eval_preset_body

    eval_default_resp = client.post(
        EVAL_DEFAULT_TMPL.format(compare_report_id=persisted_compare_id),
        headers=headers,
        json={"persist_report": False},
    )
    assert eval_default_resp.status_code == 200
    eval_default_body = eval_default_resp.json()
    for key in (
        "preset_resolution",
        "preset_version_id",
        "preset_version_number",
        "version_resolution_source",
        "pinned_version_id",
        "interpretation_band",
        "review_required",
        "caveat",
    ):
        assert key in eval_default_body


def test_phase60_readme_contract_docs_consistency():
    readme = Path(__file__).resolve().parents[2] / "README.md"
    content = readme.read_text(encoding="utf-8")
    assert "/api/v1/ai-governance/contracts/phase5" in content
    assert "/api/v1/ai-governance/contracts/phase5/compatibility-summary" in content
    assert "/api/v1/ai-governance/contracts/phase5/{group_key}" in content
    assert "Phase 5 is closed" in content
    assert "Phase 6.0 Contract Stabilization" in content
