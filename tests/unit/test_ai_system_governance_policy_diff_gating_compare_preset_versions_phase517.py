from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_presets_phase516 import (
    _create_diff_report,
    _create_profile,
    _insert_gating_report,
)


def _create_preset(client, headers: dict[str, str], *, baseline_report_id: str, profile_id: str) -> dict:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={
            "name": "P517 Preset",
            "baseline_gating_report_id": baseline_report_id,
            "baseline_gating_profile_id": profile_id,
            "watched_reason_codes_json": ["POLICY_SET_CHANGED"],
            "ignored_reason_codes_json": ["POLICY_VERSION_CHANGED"],
            "interpretation_rules_json": {
                "severity_increase_band": "attention",
                "review_required_flip_band": "critical_review",
                "watched_reason_code_band": "review_required",
            },
            "default_interpretation_band": "stable",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_phase517_preset_versions_crud_activation_archive_and_immutability(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p517-v1")
    org2 = bootstrap_org_user(client, email_prefix="p517-v2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    diff_id = _create_diff_report(client, h1)
    profile_id = _create_profile(client, h1)
    baseline_report_id = _insert_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )
    preset = _create_preset(client, h1, baseline_report_id=baseline_report_id, profile_id=profile_id)

    v1_create = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h1,
        json={"change_reason": "initial"},
    )
    assert v1_create.status_code == 201
    v1 = v1_create.json()
    assert v1["version_number"] == 1
    assert v1["status"] == "draft"
    assert v1["snapshot_json"]["default_interpretation_band"] == "stable"

    update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=h1,
        json={"default_interpretation_band": "attention", "description": "phase517"},
    )
    assert update.status_code == 200

    v2_create = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h1,
        json={"change_reason": "second"},
    )
    assert v2_create.status_code == 201
    v2 = v2_create.json()
    assert v2["version_number"] == 2
    assert v2["snapshot_json"]["default_interpretation_band"] == "attention"

    v1_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v1['id']}",
        headers=h1,
    )
    assert v1_detail.status_code == 200
    assert v1_detail.json()["snapshot_json"]["default_interpretation_band"] == "stable"

    listed = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h1,
    )
    assert listed.status_code == 200
    assert [item["version_number"] for item in listed.json()[:2]] == [2, 1]

    cross_list = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h2,
    )
    assert cross_list.status_code == 404
    cross_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v1['id']}",
        headers=h2,
    )
    assert cross_detail.status_code == 404

    activate_v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v1['id']}/activate",
        headers=h1,
        json={"reason": "activate v1"},
    )
    assert activate_v1.status_code == 200
    assert activate_v1.json()["status"] == "active"

    activate_v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v2['id']}/activate",
        headers=h1,
        json={"reason": "activate v2"},
    )
    assert activate_v2.status_code == 200
    assert activate_v2.json()["status"] == "active"

    v1_after = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v1['id']}",
        headers=h1,
    )
    assert v1_after.status_code == 200
    assert v1_after.json()["status"] == "deprecated"

    preset_detail = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=h1,
    )
    assert preset_detail.status_code == 200
    current = next(item for item in preset_detail.json() if item["id"] == preset["id"])
    assert current["active_version_id"] == v2["id"]

    v3_create = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=h1,
        json={"change_reason": "third"},
    )
    assert v3_create.status_code == 201
    v3 = v3_create.json()
    archive_v3 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v3['id']}/archive",
        headers=h1,
        json={"reason": "archive draft"},
    )
    assert archive_v3.status_code == 200
    assert archive_v3.json()["status"] == "archived"

    archive_active = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v2['id']}/archive",
        headers=h1,
        json={"reason": "should fail"},
    )
    assert archive_active.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare_preset_version.created" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset_version.activated" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset_version.archived" in actions


def test_phase517_evaluate_uses_explicit_or_active_version_and_persisted_snapshot(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p517-eval")
    headers = org["org_headers"]

    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)
    base = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "POLICY_VERSION_CHANGED", "count": 1, "severity": "low", "review_required": False}],
    )
    compare = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="high",
        review_required=True,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "POLICY_SET_CHANGED", "count": 1, "severity": "high", "review_required": True}],
    )
    preset = _create_preset(client, headers, baseline_report_id=base, profile_id=profile_id)

    v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=headers,
        json={"change_reason": "v1"},
    )
    assert v1.status_code == 201
    v1_body = v1.json()

    update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=headers,
        json={"default_interpretation_band": "attention", "watched_reason_codes_json": ["POLICY_ASSIGNMENT_CHANGED"]},
    )
    assert update.status_code == 200
    v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=headers,
        json={"change_reason": "v2"},
    )
    assert v2.status_code == 201
    v2_body = v2.json()

    fallback_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare},
    )
    assert fallback_eval.status_code == 200
    assert fallback_eval.json()["preset_version_id"] is None
    assert fallback_eval.json()["preset_snapshot_used"]["default_interpretation_band"] == "attention"

    explicit_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare, "preset_version_id": v1_body["id"]},
    )
    assert explicit_eval.status_code == 200
    explicit_body = explicit_eval.json()
    assert explicit_body["preset_version_id"] == v1_body["id"]
    assert explicit_body["preset_version_number"] == 1
    assert explicit_body["preset_snapshot_used"]["default_interpretation_band"] == "stable"

    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v2_body['id']}/activate",
        headers=headers,
        json={"reason": "set active"},
    )
    assert activate.status_code == 200

    active_default_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare},
    )
    assert active_default_eval.status_code == 200
    assert active_default_eval.json()["preset_version_id"] == v2_body["id"]
    assert active_default_eval.json()["preset_version_number"] == 2

    active_eval = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare, "persist_report": True, "preset_version_id": v1_body["id"]},
    )
    assert active_eval.status_code == 200
    active_body = active_eval.json()
    assert active_body["persisted"] is True
    assert active_body["preset_report_id"] is not None
    assert active_body["preset_version_id"] == v1_body["id"]
    assert active_body["preset_version_number"] == 1

    report_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{active_body['preset_report_id']}",
        headers=headers,
    )
    assert report_detail.status_code == 200
    detail_body = report_detail.json()
    assert detail_body["preset_version_id"] == v1_body["id"]
    assert detail_body["preset_version_number"] == 1
    assert detail_body["preset_snapshot_json"]["default_interpretation_band"] == "stable"

    update_again = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=headers,
        json={"default_interpretation_band": "critical_review"},
    )
    assert update_again.status_code == 200
    report_detail_after = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{active_body['preset_report_id']}",
        headers=headers,
    )
    assert report_detail_after.status_code == 200
    assert report_detail_after.json()["preset_snapshot_json"]["default_interpretation_band"] == "stable"


def test_phase517_preset_summary_includes_version_counts(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p517-summary")
    headers = org["org_headers"]

    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)
    base = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )
    preset = _create_preset(client, headers, baseline_report_id=base, profile_id=profile_id)
    v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=headers,
        json={"change_reason": "v1"},
    )
    assert v1.status_code == 201
    v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions",
        headers=headers,
        json={"change_reason": "v2"},
    )
    assert v2.status_code == 201
    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v2.json()['id']}/activate",
        headers=headers,
        json={"reason": "active"},
    )
    assert activate.status_code == 200
    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/versions/{v1.json()['id']}/archive",
        headers=headers,
        json={"reason": "archive old"},
    )
    assert archive.status_code == 200

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-summary",
        headers=headers,
    )
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_preset_versions"] == 2
    assert body["active_preset_versions"] == 1
    assert body["archived_preset_versions"] == 1
    assert body["presets_without_active_version"] == 0
