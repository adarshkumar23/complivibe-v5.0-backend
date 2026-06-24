from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_presets_phase516 import (
    _create_diff_report,
    _create_profile,
    _insert_gating_report,
)


def _create_context(client, db_session, headers: dict[str, str], organization_id: str) -> tuple[str, str, str]:
    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)
    base_id = _insert_gating_report(
        db_session,
        organization_id=organization_id,
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}
        ],
    )
    compare_id = _insert_gating_report(
        db_session,
        organization_id=organization_id,
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[
            {"reason_code": "POLICY_SET_CHANGED", "count": 1, "severity": "high", "review_required": True}
        ],
    )
    return profile_id, base_id, compare_id


def test_phase518_pin_unpin_validation_status_and_audit(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p518-pin-1")
    org2 = bootstrap_org_user(client, email_prefix="p518-pin-2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    profile_id, base_id, _ = _create_context(client, db_session, h1, org1["organization_id"])
    preset = _create_preset(client, h1, baseline_report_id=base_id, profile_id=profile_id)

    v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h1,
        json={"change_reason": "v1"},
    )
    assert v1.status_code == 201
    v1_id = v1.json()["id"]

    missing_reason_pin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=h1,
        json={"version_id": v1_id},
    )
    assert missing_reason_pin.status_code == 422

    pinned = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=h1,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": True,
            "reason": "freeze interpretation baseline",
        },
    )
    assert pinned.status_code == 200
    pinned_body = pinned.json()
    assert pinned_body["pinned_version_id"] == v1_id
    assert pinned_body["version_selection_mode"] == "pinned_preferred"
    assert pinned_body["allow_explicit_version_override"] is True
    assert pinned_body["pin_reason"] == "freeze interpretation baseline"

    status_resp = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pinning-status",
        headers=h1,
    )
    assert status_resp.status_code == 200
    status_body = status_resp.json()
    assert status_body["preset_id"] == preset["id"]
    assert status_body["pinned_version_id"] == v1_id
    assert status_body["pinned_version_number"] == 1
    assert status_body["version_selection_mode"] == "pinned_preferred"
    assert status_body["pin_reason"] == "freeze interpretation baseline"

    missing_reason_unpin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/unpin-version",
        headers=h1,
        json={},
    )
    assert missing_reason_unpin.status_code == 422

    unpinned = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/unpin-version",
        headers=h1,
        json={"reason": "return to default behavior"},
    )
    assert unpinned.status_code == 200
    assert unpinned.json()["pinned_version_id"] is None
    assert unpinned.json()["version_selection_mode"] == "active_then_mutable"
    assert unpinned.json()["unpin_reason"] == "return to default behavior"

    second_preset = _create_preset(client, h1, baseline_report_id=base_id, profile_id=profile_id)
    second_v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{second_preset['id']}/versions",
        headers=h1,
        json={"change_reason": "other preset"},
    )
    assert second_v1.status_code == 201
    wrong_preset_pin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=h1,
        json={"version_id": second_v1.json()["id"], "reason": "bad"},
    )
    assert wrong_preset_pin.status_code == 404

    profile_id_2, base_id_2, _ = _create_context(client, db_session, h2, org2["organization_id"])
    preset_other_org = _create_preset(client, h2, baseline_report_id=base_id_2, profile_id=profile_id_2)
    other_version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_other_org['id']}/versions",
        headers=h2,
        json={"change_reason": "foreign"},
    )
    assert other_version.status_code == 201
    cross_org_pin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=h1,
        json={"version_id": other_version.json()["id"], "reason": "bad"},
    )
    assert cross_org_pin.status_code == 404

    archived_version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h1,
        json={"change_reason": "archive me"},
    )
    assert archived_version.status_code == 201
    archived_version_id = archived_version.json()["id"]
    archived_resp = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{archived_version_id}/archive",
        headers=h1,
        json={"reason": "archive"},
    )
    assert archived_resp.status_code == 200
    pin_archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=h1,
        json={"version_id": archived_version_id, "reason": "no"},
    )
    assert pin_archived.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare_preset.version_pinned" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset.version_unpinned" in actions


def test_phase518_evaluate_respects_pinning_modes_and_override_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p518-eval")
    headers = org["org_headers"]

    profile_id, base_id, compare_id = _create_context(client, db_session, headers, org["organization_id"])
    preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)

    v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=headers,
        json={"change_reason": "v1"},
    )
    assert v1.status_code == 201
    v1_id = v1.json()["id"]
    v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=headers,
        json={"change_reason": "v2"},
    )
    assert v2.status_code == 201
    v2_id = v2.json()["id"]

    pinned_preferred = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": True,
            "reason": "default to v1",
        },
    )
    assert pinned_preferred.status_code == 200

    pinned_default_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare_id},
    )
    assert pinned_default_eval.status_code == 200
    assert pinned_default_eval.json()["preset_version_id"] == v1_id
    assert pinned_default_eval.json()["version_resolution_source"] == "pinned_version"
    assert pinned_default_eval.json()["explicit_version_override_used"] is False

    missing_override_reason = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare_id, "preset_version_id": v2_id},
    )
    assert missing_override_reason.status_code == 400

    override_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={
            "compare_gating_report_id": compare_id,
            "preset_version_id": v2_id,
            "version_override_reason": "operator override approved",
        },
    )
    assert override_eval.status_code == 200
    override_body = override_eval.json()
    assert override_body["preset_version_id"] == v2_id
    assert override_body["version_resolution_source"] == "explicit_version"
    assert override_body["explicit_version_override_used"] is True
    assert override_body["version_override_reason"] == "operator override approved"

    disallow_override = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": False,
            "reason": "lock pin",
        },
    )
    assert disallow_override.status_code == 200
    blocked_override = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={
            "compare_gating_report_id": compare_id,
            "preset_version_id": v2_id,
            "version_override_reason": "should fail",
        },
    )
    assert blocked_override.status_code == 400

    pinned_required = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": v1_id,
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": True,
            "reason": "strict mode",
        },
    )
    assert pinned_required.status_code == 200
    eval_required = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare_id},
    )
    assert eval_required.status_code == 200
    assert eval_required.json()["preset_version_id"] == v1_id
    assert eval_required.json()["version_resolution_source"] == "pinned_version"

    unpin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/unpin-version",
        headers=headers,
        json={"reason": "remove pin"},
    )
    assert unpin.status_code == 200
    make_required_without_pin = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=headers,
        json={"version_selection_mode": "pinned_required"},
    )
    assert make_required_without_pin.status_code == 200
    required_without_pin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare_id},
    )
    assert required_without_pin.status_code == 400

    reset_mode = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=headers,
        json={"version_selection_mode": "active_then_mutable"},
    )
    assert reset_mode.status_code == 200
    activate_v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v2_id}/activate",
        headers=headers,
        json={"reason": "active v2"},
    )
    assert activate_v2.status_code == 200
    active_then_mutable_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare_id},
    )
    assert active_then_mutable_eval.status_code == 200
    assert active_then_mutable_eval.json()["preset_version_id"] == v2_id
    assert active_then_mutable_eval.json()["version_resolution_source"] == "active_version"


def test_phase518_persisted_report_metadata_and_summary_pinning_counters(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p518-summary")
    headers = org["org_headers"]

    profile_id, base_id, compare_id = _create_context(client, db_session, headers, org["organization_id"])
    preset1 = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset2 = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)

    p1v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset1['id']}/versions",
        headers=headers,
        json={"change_reason": "p1v1"},
    )
    assert p1v1.status_code == 201
    p2v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset2['id']}/versions",
        headers=headers,
        json={"change_reason": "p2v1"},
    )
    assert p2v1.status_code == 201

    pin1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset1['id']}/pin-version",
        headers=headers,
        json={
            "version_id": p1v1.json()["id"],
            "version_selection_mode": "pinned_preferred",
            "allow_explicit_version_override": True,
            "reason": "preferred",
        },
    )
    assert pin1.status_code == 200
    pin2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset2['id']}/pin-version",
        headers=headers,
        json={
            "version_id": p2v1.json()["id"],
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": False,
            "reason": "required",
        },
    )
    assert pin2.status_code == 200

    persisted_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset2['id']}/evaluate",
        headers=headers,
        json={
            "compare_gating_report_id": compare_id,
            "persist_report": True,
        },
    )
    assert persisted_eval.status_code == 200
    eval_body = persisted_eval.json()
    assert eval_body["persisted"] is True
    assert eval_body["preset_report_id"] is not None
    assert eval_body["version_resolution_source"] == "pinned_version"
    assert eval_body["pinned_version_id"] == p2v1.json()["id"]
    assert eval_body["explicit_version_override_used"] is False

    report_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{eval_body['preset_report_id']}",
        headers=headers,
    )
    assert report_detail.status_code == 200
    result_json = report_detail.json()["result_json"]
    assert result_json["version_resolution_source"] == "pinned_version"
    assert result_json["pinned_version_id"] == p2v1.json()["id"]
    assert result_json["explicit_version_override_used"] is False

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["pinned_presets"] == 2
    assert summary_body["pinned_preferred_presets"] == 1
    assert summary_body["pinned_required_presets"] == 1
    assert summary_body["presets_allowing_explicit_override"] >= 1
    assert summary_body["presets_blocking_explicit_override"] >= 1

