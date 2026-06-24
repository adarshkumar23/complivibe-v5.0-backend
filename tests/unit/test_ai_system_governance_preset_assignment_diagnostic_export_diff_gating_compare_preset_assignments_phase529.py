import uuid

from sqlalchemy import select

from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment_history import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_report import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_report import (
    AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
)
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_preset_versions_phase528 import (
    _create_context,
    _version_endpoints,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_presets_phase527 import (
    PRESET_BASE,
    _create_preset,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525 import _create_profile

ASSIGNMENT_BASE = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-assignments"
)
RESOLVE_ENDPOINT = f"{ASSIGNMENT_BASE}/resolve"
SUMMARY_ENDPOINT = f"{ASSIGNMENT_BASE}/summary"
EVAL_DEFAULT_TMPL = (
    "/api/v1/ai-governance/guardrails/policy-resolution/"
    "diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-reports/{compare_report_id}/"
    "evaluate-default-preset"
)


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


def _create_assignment(client, headers: dict[str, str], **overrides) -> dict:
    payload = {
        "preset_id": overrides.pop("preset_id"),
        "scope_type": overrides.pop("scope_type", "all_ai_governance"),
        "reason": overrides.pop("reason", "phase529 create"),
        "status": overrides.pop("status", "active"),
        "priority": overrides.pop("priority", 100),
    }
    payload.update(overrides)
    response = client.post(ASSIGNMENT_BASE, headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase529_assignment_crud_history_and_scope_validation(client, db_session):
    org, headers, compare_report_id, _ = _create_context(client, db_session, "p529-crud")
    preset = _create_preset(client, headers, interpretation_rules_json={})
    sequence_pack_id = _create_sequence_pack(client, headers, name="P529 Pack")
    ai_system_id = _create_ai_system(client, headers, name="P529 System")
    profile = _create_profile(client, headers)

    missing_reason = client.post(
        ASSIGNMENT_BASE,
        headers=headers,
        json={"preset_id": preset["id"], "scope_type": "all_ai_governance", "reason": ""},
    )
    assert missing_reason.status_code == 422

    invalid_scope = client.post(
        ASSIGNMENT_BASE,
        headers=headers,
        json={"preset_id": preset["id"], "scope_type": "not_real", "reason": "bad"},
    )
    assert invalid_scope.status_code == 422

    invalid_export_type = client.post(
        ASSIGNMENT_BASE,
        headers=headers,
        json={
            "preset_id": preset["id"],
            "scope_type": "export_type",
            "scope_json": {"export_type": "bogus"},
            "reason": "bad",
        },
    )
    assert invalid_export_type.status_code == 400

    compare_scope = _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="diagnostic_export_diff_gating_compare_report",
        scope_id=compare_report_id,
    )
    profile_scope = _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="diagnostic_export_diff_gating_profile",
        scope_id=profile["id"],
        priority=90,
    )
    pack_scope = _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="sequence_pack",
        scope_id=sequence_pack_id,
        priority=80,
    )
    _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="ai_system",
        scope_id=ai_system_id,
        priority=70,
    )
    _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="review_type",
        scope_json={"review_type": "pre_production_review"},
        priority=60,
    )
    _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="rollout_class",
        scope_json={"rollout_class": "pilot"},
        priority=50,
    )
    _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="export_type",
        scope_json={"export_type": "diagnostic_diff_report"},
        priority=40,
    )
    global_assignment = _create_assignment(client, headers, preset_id=preset["id"], priority=10)

    duplicate_exact = client.post(
        ASSIGNMENT_BASE,
        headers=headers,
        json={
            "preset_id": preset["id"],
            "scope_type": "all_ai_governance",
            "reason": "dup",
            "priority": 10,
        },
    )
    assert duplicate_exact.status_code == 400

    listing = client.get(ASSIGNMENT_BASE, headers=headers)
    assert listing.status_code == 200
    ids = {row["id"] for row in listing.json()}
    assert compare_scope["id"] in ids
    assert profile_scope["id"] in ids

    updated = client.patch(
        f"{ASSIGNMENT_BASE}/{global_assignment['id']}",
        headers=headers,
        json={"priority": 11, "status": "inactive", "reason": "changed"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 11
    assert updated.json()["status"] == "inactive"

    archived = client.post(
        f"{ASSIGNMENT_BASE}/{global_assignment['id']}/archive",
        headers=headers,
        json={"reason": "archive it"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    history = client.get(f"{ASSIGNMENT_BASE}/{global_assignment['id']}/history", headers=headers)
    assert history.status_code == 200
    events = [row["event_type"] for row in history.json()]
    assert "created" in events
    assert "updated" in events
    assert "archived" in events

    # Tenant validation for compare_report / gating_profile scopes.
    other = bootstrap_org_user(client, email_prefix="p529-crud-other")
    cross_compare = client.post(
        ASSIGNMENT_BASE,
        headers=other["org_headers"],
        json={
            "preset_id": _create_preset(client, other["org_headers"], interpretation_rules_json={})["id"],
            "scope_type": "diagnostic_export_diff_gating_compare_report",
            "scope_id": compare_report_id,
            "reason": "cross",
        },
    )
    assert cross_compare.status_code == 404

    cross_profile = client.post(
        ASSIGNMENT_BASE,
        headers=other["org_headers"],
        json={
            "preset_id": _create_preset(client, other["org_headers"], interpretation_rules_json={})["id"],
            "scope_type": "diagnostic_export_diff_gating_profile",
            "scope_id": profile["id"],
            "reason": "cross",
        },
    )
    assert cross_profile.status_code == 404


def test_phase529_resolution_precedence_and_evaluate_default_with_pinning(client, db_session):
    org, headers, compare_report_id, compare_gating_report_id = _create_context(client, db_session, "p529-resolve")
    compare_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == uuid.UUID(compare_report_id)
        )
    ).scalar_one()
    preset_global = _create_preset(client, headers, name="Global", interpretation_rules_json={})
    preset_profile = _create_preset(client, headers, name="Profile", interpretation_rules_json={})
    preset_compare = _create_preset(client, headers, name="Compare", interpretation_rules_json={})

    profile = _create_profile(client, headers)

    _create_assignment(client, headers, preset_id=preset_global["id"], scope_type="all_ai_governance", priority=10)
    _create_assignment(
        client,
        headers,
        preset_id=preset_profile["id"],
        scope_type="diagnostic_export_diff_gating_profile",
        scope_id=profile["id"],
        priority=50,
    )
    _create_assignment(
        client,
        headers,
        preset_id=preset_compare["id"],
        scope_type="diagnostic_export_diff_gating_compare_report",
        scope_id=compare_report_id,
        priority=30,
    )

    resolve = client.post(
        RESOLVE_ENDPOINT,
        headers=headers,
        json={
            "compare_report_id": compare_report_id,
            "gating_profile_id": profile["id"],
            "export_type": "diagnostic_diff_report",
        },
    )
    assert resolve.status_code == 200
    resolved = resolve.json()
    assert resolved["resolved_preset_id"] == preset_compare["id"]
    assert resolved["resolution_source"] == "mapped_diagnostic_export_diff_gating_compare_report"
    assert any(item["scope_type"] == "diagnostic_export_diff_gating_compare_report" for item in resolved["precedence_trace"])

    resolve_explicit = client.post(
        RESOLVE_ENDPOINT,
        headers=headers,
        json={
            "explicit_preset_id": preset_global["id"],
            "compare_report_id": compare_report_id,
            "gating_profile_id": profile["id"],
        },
    )
    assert resolve_explicit.status_code == 200
    assert resolve_explicit.json()["resolution_source"] == "explicit_request"
    assert resolve_explicit.json()["resolved_preset_id"] == preset_global["id"]

    # Pinning/version-aware behavior remains preserved through evaluate-default-preset.
    v1 = client.post(_version_endpoints(preset_compare["id"]), headers=headers, json={"change_reason": "v1"})
    assert v1.status_code == 201
    v2 = client.post(_version_endpoints(preset_compare["id"]), headers=headers, json={"change_reason": "v2"})
    assert v2.status_code == 201
    v1_id = v1.json()["id"]
    v2_id = v2.json()["id"]

    pin_required = client.post(
        f"{PRESET_BASE}/{preset_compare['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": False,
            "reason": "lock",
        },
    )
    assert pin_required.status_code == 200

    default_eval = client.post(
        EVAL_DEFAULT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={
            "gating_profile_id": profile["id"],
            "persist_report": True,
        },
    )
    assert default_eval.status_code == 200
    body = default_eval.json()
    assert body["preset_resolution"]["resolution_source"] == "mapped_diagnostic_export_diff_gating_compare_report"
    assert body["preset_id"] == preset_compare["id"]
    assert body["version_resolution_source"] == "pinned_version"
    assert body["preset_version_id"] == v1_id

    detail = client.get(
        (
            "/api/v1/ai-governance/guardrails/policy-resolution/"
            f"diff-gating-compare-preset-assignments/diagnostic-export-diff-gating-compare-preset-reports/{body['preset_report_id']}"
        ),
        headers=headers,
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["preset_version_id"] == v1_id
    assert detail_body["version_resolution_source"] == "pinned_version"

    report_row = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id == uuid.UUID(body["preset_report_id"])
        )
    ).scalar_one()
    assert isinstance(report_row.result_json, dict)
    assert report_row.result_json["preset_resolution"]["resolution_source"] == "mapped_diagnostic_export_diff_gating_compare_report"

    blocked_override = client.post(
        EVAL_DEFAULT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={
            "explicit_preset_id": preset_compare["id"],
            "preset_version_id": v2_id,
            "version_override_reason": "try override",
        },
    )
    assert blocked_override.status_code == 400

    # Explicit preset still wins when provided.
    explicit_eval = client.post(
        EVAL_DEFAULT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={
            "explicit_preset_id": preset_global["id"],
            "gating_profile_id": profile["id"],
        },
    )
    assert explicit_eval.status_code == 200
    assert explicit_eval.json()["preset_resolution"]["resolution_source"] == "explicit_request"
    assert explicit_eval.json()["preset_id"] == preset_global["id"]

    # Inactive mapped preset should fail resolution.
    deactivate_compare_preset = client.patch(
        f"{PRESET_BASE}/{preset_compare['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert deactivate_compare_preset.status_code == 200
    inactive_eval = client.post(
        EVAL_DEFAULT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"gating_profile_id": profile["id"]},
    )
    assert inactive_eval.status_code == 400

    compare_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == uuid.UUID(compare_report_id)
        )
    ).scalar_one()
    assert compare_after.updated_at == compare_before.updated_at


def test_phase529_summary_audit_and_no_source_mutation(client, db_session):
    org, headers, compare_report_id, _ = _create_context(client, db_session, "p529-summary")
    preset = _create_preset(client, headers, interpretation_rules_json={})

    created = _create_assignment(
        client,
        headers,
        preset_id=preset["id"],
        scope_type="all_ai_governance",
        reason="create",
    )

    updated = client.patch(
        f"{ASSIGNMENT_BASE}/{created['id']}",
        headers=headers,
        json={"priority": 321, "reason": "update"},
    )
    assert updated.status_code == 200

    archived = client.post(
        f"{ASSIGNMENT_BASE}/{created['id']}/archive",
        headers=headers,
        json={"reason": "archive"},
    )
    assert archived.status_code == 200

    summary = client.get(SUMMARY_ENDPOINT, headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_assignments"] >= 0
    assert body["archived_assignments"] >= 1
    assert body["highest_priority"] >= 321
    assert "all_ai_governance" in body["by_scope_type"]

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment.created" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment.updated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_assignment.archived" in actions

    history_rows = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory.assignment_id
            == uuid.UUID(created["id"])
        )
    ).scalars().all()
    assert len(history_rows) >= 3

    assignment_row = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment.id == uuid.UUID(created["id"])
        )
    ).scalar_one()
    assert assignment_row.status == "archived"
