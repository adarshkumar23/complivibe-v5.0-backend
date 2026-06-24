import uuid

from sqlalchemy import select

from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_report import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_preset_version import (
    AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_compare_report import (
    AISystemGovernanceDiagnosticExportDiffGatingCompareReport,
)
from app.models.ai_system_governance_diagnostic_export_diff_gating_report import (
    AISystemGovernanceDiagnosticExportDiffGatingReport,
)
from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_phase526 import (
    _insert_diag_export_diff_gating_report,
    _make_export_diff_report,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_compare_presets_phase527 import (
    PRESET_BASE,
    PRESET_REPORT_BASE,
    PRESET_SUMMARY_ENDPOINT,
    EVAL_ENDPOINT_TMPL,
    _create_compare_report,
    _create_preset,
)
from tests.unit.test_ai_system_governance_preset_assignment_diagnostic_export_diff_gating_phase525 import _create_profile


def _create_context(client, db_session, email_prefix: str) -> tuple[dict, dict, str, str]:
    org, headers, export_diff_report_id = _make_export_diff_report(client, db_session, email_prefix=email_prefix)
    profile = _create_profile(client, headers)
    base_id = _insert_diag_export_diff_gating_report(
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
    compare_id = _insert_diag_export_diff_gating_report(
        db_session,
        organization_id=org["organization_id"],
        export_diff_report_id=export_diff_report_id,
        profile_id=profile["id"],
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "EXPORT_PAYLOAD_HASH_CHANGED", "count": 1, "severity": "high", "review_required": True}
        ],
    )
    compare_report_id = _create_compare_report(
        db_session,
        organization_id=org["organization_id"],
        base_gating_report_id=base_id,
        compare_gating_report_id=compare_id,
        max_severity_drift="increased",
        review_required_drift="became_required",
        added_reason_codes=["EXPORT_PATH_CHANGED"],
        removed_reason_codes=[],
        changed_reason_codes=[],
        reason_code_changes_count=1,
        severity_changes_count=0,
    )
    return org, headers, compare_report_id, compare_id


def _version_endpoints(preset_id: str, version_id: str | None = None) -> str:
    base = f"{PRESET_BASE}/{preset_id}/versions"
    if version_id is None:
        return base
    return f"{base}/{version_id}"


def test_phase528_version_crud_activation_archive_and_snapshot_immutability(client, db_session):
    org, headers, compare_report_id, _ = _create_context(client, db_session, "p528-vcrud")
    preset = _create_preset(
        client,
        headers,
        interpretation_rules_json={"severity_increase_band": "review_required"},
    )

    create_v1 = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "v1"})
    assert create_v1.status_code == 201
    v1 = create_v1.json()
    assert v1["version_number"] == 1
    assert v1["status"] == "draft"
    assert v1["snapshot_json"]["default_interpretation_band"] == "stable"

    update_preset = client.patch(
        f"{PRESET_BASE}/{preset['id']}",
        headers=headers,
        json={"default_interpretation_band": "attention"},
    )
    assert update_preset.status_code == 200

    create_v2 = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "v2"})
    assert create_v2.status_code == 201
    v2 = create_v2.json()
    assert v2["version_number"] == 2
    assert v2["snapshot_json"]["default_interpretation_band"] == "attention"

    detail_v1 = client.get(_version_endpoints(preset["id"], v1["id"]), headers=headers)
    assert detail_v1.status_code == 200
    assert detail_v1.json()["snapshot_json"]["default_interpretation_band"] == "stable"

    listed = client.get(_version_endpoints(preset["id"]), headers=headers)
    assert listed.status_code == 200
    assert [row["version_number"] for row in listed.json()[:2]] == [2, 1]

    activate_v1 = client.post(
        f"{_version_endpoints(preset['id'], v1['id'])}/activate",
        headers=headers,
        json={"reason": "activate 1"},
    )
    assert activate_v1.status_code == 200
    assert activate_v1.json()["status"] == "active"
    activate_v2 = client.post(
        f"{_version_endpoints(preset['id'], v2['id'])}/activate",
        headers=headers,
        json={"reason": "activate 2"},
    )
    assert activate_v2.status_code == 200

    v1_after = client.get(_version_endpoints(preset["id"], v1["id"]), headers=headers)
    assert v1_after.status_code == 200
    assert v1_after.json()["status"] == "deprecated"

    archive_active = client.post(
        f"{_version_endpoints(preset['id'], v2['id'])}/archive",
        headers=headers,
        json={"reason": "must fail"},
    )
    assert archive_active.status_code == 400

    draft = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "draft"})
    assert draft.status_code == 201
    archive_draft = client.post(
        f"{_version_endpoints(preset['id'], draft.json()['id'])}/archive",
        headers=headers,
        json={"reason": "archive draft"},
    )
    assert archive_draft.status_code == 200
    assert archive_draft.json()["status"] == "archived"

    pin_v1 = client.post(
        f"{PRESET_BASE}/{preset['id']}/pin-version",
        headers=headers,
        json={"version_id": v1["id"], "reason": "pin for test"},
    )
    assert pin_v1.status_code == 200
    archive_pinned = client.post(
        f"{_version_endpoints(preset['id'], v1['id'])}/archive",
        headers=headers,
        json={"reason": "must fail pinned"},
    )
    assert archive_pinned.status_code == 400

    persisted = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"], "persist_report": True, "preset_version_id": v1["id"]},
    )
    assert persisted.status_code == 200
    preset_report_id = persisted.json()["preset_report_id"]
    archive_report = client.post(
        f"{PRESET_REPORT_BASE}/{preset_report_id}/archive",
        headers=headers,
        json={"reason": "archive endpoint exists"},
    )
    assert archive_report.status_code == 200
    assert archive_report.json()["status"] == "archived"


def test_phase528_pin_unpin_status_and_cross_tenant_validation(client, db_session):
    org1, h1, compare_1, _ = _create_context(client, db_session, "p528-pin-1")
    org2, h2, compare_2, _ = _create_context(client, db_session, "p528-pin-2")
    preset1 = _create_preset(client, h1, interpretation_rules_json={})
    preset2 = _create_preset(client, h2, interpretation_rules_json={})

    v1 = client.post(_version_endpoints(preset1["id"]), headers=h1, json={"change_reason": "v1"})
    assert v1.status_code == 201
    v1_id = v1.json()["id"]
    v2_other = client.post(_version_endpoints(preset2["id"]), headers=h2, json={"change_reason": "other"})
    assert v2_other.status_code == 201

    missing_reason_pin = client.post(
        f"{PRESET_BASE}/{preset1['id']}/pin-version",
        headers=h1,
        json={"version_id": v1_id},
    )
    assert missing_reason_pin.status_code == 422

    cross_pin = client.post(
        f"{PRESET_BASE}/{preset1['id']}/pin-version",
        headers=h1,
        json={"version_id": v2_other.json()["id"], "reason": "bad"},
    )
    assert cross_pin.status_code == 404

    pin = client.post(
        f"{PRESET_BASE}/{preset1['id']}/pin-version",
        headers=h1,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": True,
            "reason": "pin now",
        },
    )
    assert pin.status_code == 200
    assert pin.json()["pinned_version_id"] == v1_id

    status_resp = client.get(f"{PRESET_BASE}/{preset1['id']}/pinning-status", headers=h1)
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["preset_id"] == preset1["id"]
    assert status_body["pinned_version_id"] == v1_id
    assert status_body["pinned_version_number"] == 1
    assert status_body["version_selection_mode"] == "pinned_preferred"

    missing_reason_unpin = client.post(
        f"{PRESET_BASE}/{preset1['id']}/unpin-version",
        headers=h1,
        json={},
    )
    assert missing_reason_unpin.status_code == 422
    unpin = client.post(
        f"{PRESET_BASE}/{preset1['id']}/unpin-version",
        headers=h1,
        json={"reason": "unpin now"},
    )
    assert unpin.status_code == 200
    assert unpin.json()["pinned_version_id"] is None
    assert unpin.json()["version_selection_mode"] == "active_then_mutable"

    # Tenant scope still applies on evaluate after pin/unpin operations.
    cross_eval = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_2),
        headers=h1,
        json={"preset_id": preset1["id"], "persist_report": False},
    )
    assert cross_eval.status_code == 404
    own_eval = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_1),
        headers=h1,
        json={"preset_id": preset1["id"], "persist_report": False},
    )
    assert own_eval.status_code == 200


def test_phase528_evaluate_version_resolution_and_persisted_snapshot_metadata(client, db_session):
    org, headers, compare_report_id, compare_gating_id = _create_context(client, db_session, "p528-eval")
    preset = _create_preset(client, headers, interpretation_rules_json={})

    v1 = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "v1"})
    assert v1.status_code == 201
    v1_id = v1.json()["id"]
    update_preset = client.patch(
        f"{PRESET_BASE}/{preset['id']}",
        headers=headers,
        json={"default_interpretation_band": "attention"},
    )
    assert update_preset.status_code == 200
    v2 = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "v2"})
    assert v2.status_code == 201
    v2_id = v2.json()["id"]

    compare_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == uuid.UUID(compare_report_id)
        )
    ).scalar_one()
    gating_before = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(compare_gating_id)
        )
    ).scalar_one()

    fallback_eval = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"], "persist_report": False},
    )
    assert fallback_eval.status_code == 200
    assert fallback_eval.json()["version_resolution_source"] == "mutable_preset"
    assert fallback_eval.json()["preset_version_id"] is None

    activate_v2 = client.post(
        f"{_version_endpoints(preset['id'], v2_id)}/activate",
        headers=headers,
        json={"reason": "active"},
    )
    assert activate_v2.status_code == 200
    active_eval = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"]},
    )
    assert active_eval.status_code == 200
    assert active_eval.json()["version_resolution_source"] == "active_version"
    assert active_eval.json()["preset_version_id"] == v2_id

    pin_preferred = client.post(
        f"{PRESET_BASE}/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": True,
            "reason": "pin preferred",
        },
    )
    assert pin_preferred.status_code == 200

    pinned_eval = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"]},
    )
    assert pinned_eval.status_code == 200
    assert pinned_eval.json()["version_resolution_source"] == "pinned_version"
    assert pinned_eval.json()["preset_version_id"] == v1_id

    blocked_missing_reason = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"], "preset_version_id": v2_id},
    )
    assert blocked_missing_reason.status_code == 400

    explicit_override = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={
            "preset_id": preset["id"],
            "preset_version_id": v2_id,
            "version_override_reason": "approved exception",
            "persist_report": True,
        },
    )
    assert explicit_override.status_code == 200
    body = explicit_override.json()
    assert body["persisted"] is True
    assert body["preset_version_id"] == v2_id
    assert body["version_resolution_source"] == "explicit_version"
    assert body["explicit_version_override_used"] is True
    assert body["version_override_reason"] == "approved exception"
    assert body["preset_snapshot_used"]["default_interpretation_band"] == "attention"

    report_detail = client.get(f"{PRESET_REPORT_BASE}/{body['preset_report_id']}", headers=headers)
    assert report_detail.status_code == 200
    detail = report_detail.json()
    assert detail["preset_version_id"] == v2_id
    assert detail["preset_version_number"] == 2
    assert detail["version_resolution_source"] == "explicit_version"
    assert detail["explicit_version_override_used"] is True
    assert detail["version_override_reason"] == "approved exception"
    assert detail["preset_snapshot_json"]["default_interpretation_band"] == "attention"

    report_row = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport.id == uuid.UUID(body["preset_report_id"])
        )
    ).scalar_one()
    assert report_row.preset_version_id == uuid.UUID(v2_id)
    assert report_row.preset_version_number == 2
    assert report_row.version_resolution_source == "explicit_version"
    assert report_row.explicit_version_override_used is True

    pin_locked = client.post(
        f"{PRESET_BASE}/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": False,
            "reason": "locked",
        },
    )
    assert pin_locked.status_code == 200
    blocked_override = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={
            "preset_id": preset["id"],
            "preset_version_id": v2_id,
            "version_override_reason": "should fail",
        },
    )
    assert blocked_override.status_code == 400

    set_required = client.post(
        f"{PRESET_BASE}/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": True,
            "reason": "required",
        },
    )
    assert set_required.status_code == 200
    required_ok = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"]},
    )
    assert required_ok.status_code == 200
    assert required_ok.json()["version_resolution_source"] == "pinned_version"
    assert required_ok.json()["preset_version_id"] == v1_id

    unpin = client.post(f"{PRESET_BASE}/{preset['id']}/unpin-version", headers=headers, json={"reason": "clear"})
    assert unpin.status_code == 200
    force_required = client.patch(
        f"{PRESET_BASE}/{preset['id']}",
        headers=headers,
        json={"version_selection_mode": "pinned_required"},
    )
    assert force_required.status_code == 200
    required_without_pin = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"]},
    )
    assert required_without_pin.status_code == 400

    compare_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingCompareReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingCompareReport.id == uuid.UUID(compare_report_id)
        )
    ).scalar_one()
    gating_after = db_session.execute(
        select(AISystemGovernanceDiagnosticExportDiffGatingReport).where(
            AISystemGovernanceDiagnosticExportDiffGatingReport.id == uuid.UUID(compare_gating_id)
        )
    ).scalar_one()
    assert compare_after.updated_at == compare_before.updated_at
    assert gating_after.updated_at == gating_before.updated_at


def test_phase528_summary_counters_and_audit_logs(client, db_session):
    org, headers, compare_report_id, _ = _create_context(client, db_session, "p528-summary")
    preset = _create_preset(client, headers, interpretation_rules_json={})

    v1 = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "v1"})
    assert v1.status_code == 201
    v2 = client.post(_version_endpoints(preset["id"]), headers=headers, json={"change_reason": "v2"})
    assert v2.status_code == 201
    activate = client.post(
        f"{_version_endpoints(preset['id'], v2.json()['id'])}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activate.status_code == 200
    pin = client.post(
        f"{PRESET_BASE}/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1.json()["id"],
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": False,
            "reason": "pin",
        },
    )
    assert pin.status_code == 200

    eval_resp = client.post(
        EVAL_ENDPOINT_TMPL.format(compare_report_id=compare_report_id),
        headers=headers,
        json={"preset_id": preset["id"], "persist_report": True},
    )
    assert eval_resp.status_code == 200
    report_id = eval_resp.json()["preset_report_id"]

    summary = client.get(PRESET_SUMMARY_ENDPOINT, headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_preset_versions"] >= 2
    assert body["active_preset_versions"] >= 1
    assert body["draft_preset_versions"] >= 1
    assert body["pinned_presets"] >= 1
    assert body["pinned_required_presets"] >= 1
    assert body["presets_blocking_explicit_override"] >= 1

    archive_report = client.post(
        f"{PRESET_REPORT_BASE}/{report_id}/archive",
        headers=headers,
        json={"reason": "archive"},
    )
    assert archive_report.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_version.created" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_version.activated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset.version_pinned" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.generated" in actions
    assert "ai_system_governance_diagnostic_export_diff_gating_compare_preset_report.archived" in actions
