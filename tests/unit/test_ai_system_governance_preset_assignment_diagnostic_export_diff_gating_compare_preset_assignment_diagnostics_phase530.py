import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePreset,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory,
)
from app.models.audit_log import AuditLog
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_assignments_phase529 import (
    ASSIGNMENT_BASE,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_versions_phase528 import (
    _create_context,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_presets_phase527 import (
    PRESET_BASE,
    _create_preset,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525 import (
    _create_profile,
)

COVERAGE_DIAGNOSTICS_ENDPOINT = f"{ASSIGNMENT_BASE}/coverage-diagnostics"
HEALTH_DIAGNOSTICS_ENDPOINT = f"{ASSIGNMENT_BASE}/health-diagnostics"
COVERAGE_SUMMARY_ENDPOINT = f"{ASSIGNMENT_BASE}/coverage-summary"


def _create_assignment(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post(ASSIGNMENT_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> str:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "ai_feature"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _create_sequence_pack(client, headers: dict[str, str], *, name: str) -> str:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _set_preset_status(client, headers: dict[str, str], preset_id: str, status: str) -> None:
    response = client.patch(
        f"{PRESET_BASE}/{preset_id}",
        headers=headers,
        json={"status": status},
    )
    assert response.status_code == 200


def test_phase530_bulk_coverage_diagnostics_and_read_only_behavior(client, db_session):
    _, headers, compare_report_id, _ = _create_context(client, db_session, "p530-bulk")
    profile = _create_profile(client, headers)

    preset_global = _create_preset(client, headers, name="p530-global", interpretation_rules_json={})
    preset_explicit = _create_preset(client, headers, name="p530-explicit", interpretation_rules_json={})
    preset_compare = _create_preset(client, headers, name="p530-compare", interpretation_rules_json={})
    preset_profile = _create_preset(client, headers, name="p530-profile", interpretation_rules_json={})
    preset_rollout = _create_preset(client, headers, name="p530-rollout", interpretation_rules_json={})
    preset_export = _create_preset(client, headers, name="p530-export", interpretation_rules_json={})
    preset_inactive = _create_preset(client, headers, name="p530-inactive", interpretation_rules_json={})
    preset_archived = _create_preset(client, headers, name="p530-archived", interpretation_rules_json={})
    preset_pin_required = _create_preset(client, headers, name="p530-pin-required", interpretation_rules_json={})
    preset_pin_archived = _create_preset(client, headers, name="p530-pin-archived", interpretation_rules_json={})
    preset_ai_a = _create_preset(client, headers, name="p530-ai-a", interpretation_rules_json={})
    preset_ai_b = _create_preset(client, headers, name="p530-ai-b", interpretation_rules_json={})

    _set_preset_status(client, headers, preset_inactive["id"], "inactive")

    # Force a pinned_required preset with no pin.
    pin_required = client.post(
        f"{PRESET_BASE}/{preset_pin_required['id']}/versions",
        headers=headers,
        json={"change_reason": "pin-required"},
    )
    assert pin_required.status_code == 201
    pin_resp = client.post(
        f"{PRESET_BASE}/{preset_pin_required['id']}/pin-version",
        headers=headers,
        json={"version_id": pin_required.json()["id"], "reason": "pin required"},
    )
    assert pin_resp.status_code == 200
    unpin_resp = client.post(
        f"{PRESET_BASE}/{preset_pin_required['id']}/unpin-version",
        headers=headers,
        json={"reason": "remove pin"},
    )
    assert unpin_resp.status_code == 200
    pinned_required_row = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id == uuid.UUID(preset_pin_required["id"])
        )
    ).scalar_one()
    pinned_required_row.version_selection_mode = "pinned_required"
    pinned_required_row.pinned_version_id = None
    db_session.commit()

    # Pin to an archived version.
    pin_archived_version = client.post(
        f"{PRESET_BASE}/{preset_pin_archived['id']}/versions",
        headers=headers,
        json={"change_reason": "pin archived"},
    )
    assert pin_archived_version.status_code == 201
    pin_archived = client.post(
        f"{PRESET_BASE}/{preset_pin_archived['id']}/pin-version",
        headers=headers,
        json={"version_id": pin_archived_version.json()["id"], "reason": "pin it"},
    )
    assert pin_archived.status_code == 200
    archive_pin = client.post(
        f"{PRESET_BASE}/{preset_pin_archived['id']}/unpin-version",
        headers=headers,
        json={"reason": "temporary unpin"},
    )
    assert archive_pin.status_code == 200
    archive_version = client.post(
        f"{PRESET_BASE}/{preset_pin_archived['id']}/versions/{pin_archived_version.json()['id']}/archive",
        headers=headers,
        json={"reason": "archive for diagnostics"},
    )
    assert archive_version.status_code == 200
    repin_archived = client.post(
        f"{PRESET_BASE}/{preset_pin_archived['id']}/pin-version",
        headers=headers,
        json={"version_id": pin_archived_version.json()["id"], "reason": "repin archived"},
    )
    assert repin_archived.status_code == 400
    pin_archived_row = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingComparePreset).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePreset.id == uuid.UUID(preset_pin_archived["id"])
        )
    ).scalar_one()
    pin_archived_row.pinned_version_id = uuid.UUID(pin_archived_version.json()["id"])
    pin_archived_row.version_selection_mode = "pinned_preferred"
    db_session.commit()

    pack_primary = _create_sequence_pack(client, headers, name="P530 Pack Primary")
    pack_inactive = _create_sequence_pack(client, headers, name="P530 Pack Inactive")
    pack_archived = _create_sequence_pack(client, headers, name="P530 Pack Archived")
    pack_pin_required = _create_sequence_pack(client, headers, name="P530 Pack Pin Required")
    pack_pin_archived = _create_sequence_pack(client, headers, name="P530 Pack Pin Archived")
    ai_one = _create_ai_system(client, headers, name="P530 AI One")
    ai_two = _create_ai_system(client, headers, name="P530 AI Two")

    _create_assignment(
        client,
        headers,
        {"preset_id": preset_global["id"], "scope_type": "all_ai_governance", "reason": "global"},
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_compare["id"],
            "scope_type": "diagnostic_export_diff_gating_compare_report",
            "scope_id": compare_report_id,
            "reason": "compare wins",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_explicit["id"],
            "scope_type": "diagnostic_export_diff_gating_compare_report",
            "scope_id": compare_report_id,
            "reason": "inspect inactive",
            "status": "inactive",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_explicit["id"],
            "scope_type": "diagnostic_export_diff_gating_compare_report",
            "scope_id": compare_report_id,
            "reason": "inspect archived",
            "status": "archived",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_profile["id"],
            "scope_type": "diagnostic_export_diff_gating_profile",
            "scope_id": profile["id"],
            "priority": 80,
            "reason": "profile",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_rollout["id"],
            "scope_type": "rollout_class",
            "scope_json": {"rollout_class": "pilot"},
            "priority": 60,
            "reason": "rollout",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_export["id"],
            "scope_type": "export_type",
            "scope_json": {"export_type": "diagnostic_diff_report"},
            "priority": 50,
            "reason": "export",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_inactive["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_inactive,
            "reason": "inactive preset target",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_archived["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_archived,
            "reason": "archived preset target",
        },
    )
    _set_preset_status(client, headers, preset_archived["id"], "archived")
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_pin_required["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_pin_required,
            "reason": "pinned required",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_pin_archived["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack_pin_archived,
            "reason": "pinned archived",
        },
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_ai_a["id"], "scope_type": "ai_system", "scope_id": ai_one, "reason": "ai one"},
    )
    _create_assignment(
        client,
        headers,
        {"preset_id": preset_ai_b["id"], "scope_type": "ai_system", "scope_id": ai_two, "reason": "ai two"},
    )

    before_assignment_count = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    before_history_count = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    before_audit_count = db_session.execute(select(func.count(AuditLog.id))).scalar_one()

    response = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers,
        json={
            "contexts": [
                {
                    "context_key": "mapped-compare",
                    "compare_report_id": compare_report_id,
                    "gating_profile_id": profile["id"],
                    "export_type": "diagnostic_diff_report",
                },
                {
                    "context_key": "explicit",
                    "explicit_preset_id": preset_explicit["id"],
                    "compare_report_id": compare_report_id,
                },
                {
                    "context_key": "conflict-ai",
                    "ai_system_ids": [ai_one, ai_two],
                },
                {"context_key": "inactive-preset", "sequence_pack_id": pack_inactive},
                {"context_key": "archived-preset", "sequence_pack_id": pack_archived},
                {"context_key": "pin-required", "sequence_pack_id": pack_pin_required},
                {"context_key": "pin-archived", "sequence_pack_id": pack_pin_archived},
                {
                    "context_key": "fallback-rollout-over-export",
                    "rollout_class": "pilot",
                    "export_type": "diagnostic_diff_report",
                },
            ]
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["context_count"] == 8

    by_key = {item["context_key"]: item for item in body["contexts"]}
    assert by_key["mapped-compare"]["resolution_source"] == "mapped_diagnostic_export_diff_gating_compare_report"
    assert any(
        trace["scope_type"] == "diagnostic_export_diff_gating_compare_report"
        and trace.get("inactive_assignment_ids")
        and trace.get("archived_assignment_ids")
        for trace in by_key["mapped-compare"]["precedence_trace"]
    )
    assert any(item["code"] == "RESOLVED" for item in by_key["mapped-compare"]["diagnostics"])

    assert by_key["explicit"]["resolution_source"] == "explicit_request"
    assert any(item["code"] == "EXPLICIT_PRESET_USED" for item in by_key["explicit"]["diagnostics"])
    assert any(item["code"] == "CONFLICTING_ASSIGNMENTS_SAME_SCOPE" for item in by_key["conflict-ai"]["diagnostics"])
    assert any(item["code"] == "CROSS_SCOPE_FALLBACK_USED" for item in by_key["conflict-ai"]["diagnostics"])
    assert any(item["code"] == "ASSIGNMENT_TARGET_PRESET_INACTIVE" for item in by_key["inactive-preset"]["diagnostics"])
    assert any(item["code"] == "ASSIGNMENT_TARGET_PRESET_ARCHIVED" for item in by_key["archived-preset"]["diagnostics"])
    assert any(item["code"] == "PINNED_REQUIRED_WITHOUT_PIN" for item in by_key["pin-required"]["diagnostics"])
    assert any(item["code"] == "PINNED_VERSION_ARCHIVED" for item in by_key["pin-archived"]["diagnostics"])
    assert by_key["fallback-rollout-over-export"]["resolution_source"] == "mapped_rollout_class"
    assert any(item["code"] == "CROSS_SCOPE_FALLBACK_USED" for item in by_key["fallback-rollout-over-export"]["diagnostics"])

    after_assignment_count = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id))
    ).scalar_one()
    after_history_count = db_session.execute(
        select(func.count(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.id))
    ).scalar_one()
    after_audit_count = db_session.execute(select(func.count(AuditLog.id))).scalar_one()
    assert after_assignment_count == before_assignment_count
    assert after_history_count == before_history_count
    assert after_audit_count == before_audit_count


def test_phase530_bulk_diagnostics_no_assignment_found_and_tenant_isolation(client, db_session):
    _, headers1, compare_report_id_1, _ = _create_context(client, db_session, "p530-tenant-a")
    _, headers2, compare_report_id_2, _ = _create_context(client, db_session, "p530-tenant-b")
    profile_1 = _create_profile(client, headers1)
    profile_2 = _create_profile(client, headers2)
    pack_2 = _create_sequence_pack(client, headers2, name="P530 Tenant Pack")
    ai_2 = _create_ai_system(client, headers2, name="P530 Tenant AI")

    no_assignment = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers1,
        json={"contexts": [{"context_key": "none"}]},
    )
    assert no_assignment.status_code == 200
    body = no_assignment.json()
    assert body["resolved_contexts_count"] == 0
    assert body["unresolved_contexts_count"] == 1
    assert any(item["code"] == "NO_ASSIGNMENT_FOUND" for item in body["contexts"][0]["diagnostics"])

    cross_compare = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers1,
        json={"contexts": [{"compare_report_id": compare_report_id_2}]},
    )
    assert cross_compare.status_code == 404

    cross_profile = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers1,
        json={"contexts": [{"gating_profile_id": profile_2["id"]}]},
    )
    assert cross_profile.status_code == 404

    cross_pack = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers1,
        json={"contexts": [{"sequence_pack_id": pack_2}]},
    )
    assert cross_pack.status_code == 404

    cross_ai = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers1,
        json={"contexts": [{"ai_system_ids": [ai_2]}]},
    )
    assert cross_ai.status_code == 404

    # Sanity check same-org compare/gating profile pass validation.
    same_org = client.post(
        COVERAGE_DIAGNOSTICS_ENDPOINT,
        headers=headers1,
        json={"contexts": [{"compare_report_id": compare_report_id_1, "gating_profile_id": profile_1["id"]}]},
    )
    assert same_org.status_code == 200


def test_phase530_health_diagnostics_coverage_summary_and_readme_note(client, db_session):
    _, headers, compare_report_id, _ = _create_context(client, db_session, "p530-health")
    profile = _create_profile(client, headers)

    preset_active = _create_preset(client, headers, name="p530-health-active", interpretation_rules_json={})
    preset_inactive = _create_preset(client, headers, name="p530-health-inactive", interpretation_rules_json={})
    _set_preset_status(client, headers, preset_inactive["id"], "inactive")

    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_active["id"],
            "scope_type": "diagnostic_export_diff_gating_compare_report",
            "scope_id": compare_report_id,
            "reason": "active mapping",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "preset_id": preset_inactive["id"],
            "scope_type": "diagnostic_export_diff_gating_profile",
            "scope_id": profile["id"],
            "reason": "inactive target",
        },
    )

    health = client.get(HEALTH_DIAGNOSTICS_ENDPOINT, headers=headers)
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["active_assignments"] >= 2
    assert health_body["assignments_to_inactive_presets"] >= 1
    assert "caveat" in health_body

    summary = client.get(COVERAGE_SUMMARY_ENDPOINT, headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_active_assignments"] >= 2
    assert summary_body["total_problem_assignments"] >= 1
    assert summary_body["presets_referenced_by_assignments"] >= 2
    assert "diagnostic_export_diff_gating_compare_report" in summary_body["assignments_by_scope_type"]
    assert "caveat" in summary_body

    readme_text = Path("README.md").read_text(encoding="utf-8")
    assert "Phase 5.30" in readme_text
