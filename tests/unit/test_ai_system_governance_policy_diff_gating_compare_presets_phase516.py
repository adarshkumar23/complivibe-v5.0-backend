from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.models.ai_system_governance_policy_diff_gating_report import AISystemGovernancePolicyDiffGatingReport
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post("/api/v1/ai-systems", headers=headers, json={"name": name, "system_type": "agent"})
    assert response.status_code == 201
    return response.json()


def _create_pack(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 201
    return response.json()


def _create_policy_set(client, headers: dict[str, str], *, name: str, ack_text: str) -> dict:
    policy = client.post("/api/v1/ai-governance/guardrails/policy-sets", headers=headers, json={"name": name})
    assert policy.status_code == 201
    policy_body = policy.json()
    version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_body['id']}/versions",
        headers=headers,
        json={
            "profile_json": {
                "resolution_strategy": "deterministic_precedence_v1",
                "acknowledgement_text": ack_text,
                "allow_operator_override": True,
                "require_override_reason": True,
                "include_info_windows": True,
                "include_warn_windows": True,
                "include_block_windows": True,
                "scope_precedence_order": ["ai_system", "sequence_pack", "review_type", "all_ai_governance"],
            },
            "change_reason": "init",
        },
    )
    assert version.status_code == 201
    version_body = version.json()
    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_body['id']}/versions/{version_body['id']}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activate.status_code == 200
    return policy_body


def _assign_policy(client, headers: dict[str, str], payload: dict) -> None:
    response = client.post("/api/v1/ai-governance/guardrails/policy-assignments", headers=headers, json=payload)
    assert response.status_code == 201


def _persist_sim(client, headers: dict[str, str], contexts: list[dict], *, title: str) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={"persist_report": True, "title": title, "contexts": contexts},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    return body["report_id"]


def _create_diff_report(client, headers: dict[str, str]) -> str:
    ai = _create_ai_system(client, headers, name=f"P516 AI {uuid4()}")
    pack = _create_pack(client, headers, name=f"P516 Pack {uuid4()}")
    mapped_policy = _create_policy_set(client, headers, name=f"P516 Mapped {uuid4()}", ack_text="ACK_M")
    explicit_policy = _create_policy_set(client, headers, name=f"P516 Explicit {uuid4()}", ack_text="ACK_E")
    _assign_policy(
        client,
        headers,
        {"policy_set_id": mapped_policy["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "pack"},
    )
    now = datetime.now(UTC).replace(microsecond=0)
    base_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        title="base",
    )
    compare_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "explicit_policy_set_id": explicit_policy["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            }
        ],
        title="compare",
    )
    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={
            "base_report_id": base_report_id,
            "compare_report_id": compare_report_id,
            "persist_diff": True,
            "context_match_strategy": "context_key_then_index",
        },
    )
    assert diff.status_code == 200
    return diff.json()["diff_report_id"]


def _create_profile(client, headers: dict[str, str]) -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-profiles",
        headers=headers,
        json={
            "name": f"P516 Profile {uuid4()}",
            "default_severity": "low",
            "review_required_threshold": "high",
            "reason_code_rules_json": {},
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _insert_gating_report(
    db_session,
    *,
    organization_id: str,
    diff_report_id: str,
    profile_id: str,
    max_severity: str,
    review_required: bool,
    reason_code_count: int,
    reason_code_classifications: list[dict],
    severity_summary: dict[str, int] | None = None,
) -> str:
    row = AISystemGovernancePolicyDiffGatingReport(
        organization_id=UUID(organization_id),
        diff_report_id=UUID(diff_report_id),
        gating_profile_id=UUID(profile_id),
        status="generated",
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


def test_phase516_compare_preset_crud_validation_and_archived_update_block(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p516-preset")
    headers = org["org_headers"]

    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)
    base_report_id = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )

    invalid_band = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={
            "name": "bad",
            "default_interpretation_band": "urgent",
            "status": "active",
        },
    )
    assert invalid_band.status_code == 422

    unknown_watched = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={
            "name": "bad-watch",
            "watched_reason_codes_json": ["UNKNOWN_CODE"],
        },
    )
    assert unknown_watched.status_code == 400

    unknown_ignored = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={
            "name": "bad-ignore",
            "ignored_reason_codes_json": ["UNKNOWN_CODE"],
        },
    )
    assert unknown_ignored.status_code == 400

    other_org = bootstrap_org_user(client, email_prefix="p516-preset-other")
    other_headers = other_org["org_headers"]
    other_diff = _create_diff_report(client, other_headers)
    other_profile = _create_profile(client, other_headers)
    other_base_report_id = _insert_gating_report(
        db_session,
        organization_id=other_org["organization_id"],
        diff_report_id=other_diff,
        profile_id=other_profile,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )

    cross_tenant_baseline_report = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={"name": "cross-report", "baseline_gating_report_id": other_base_report_id},
    )
    assert cross_tenant_baseline_report.status_code == 404

    cross_tenant_baseline_profile = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={"name": "cross-profile", "baseline_gating_profile_id": other_profile},
    )
    assert cross_tenant_baseline_profile.status_code == 404

    create = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={
            "name": "P516 Preset",
            "baseline_gating_report_id": base_report_id,
            "baseline_gating_profile_id": profile_id,
            "watched_reason_codes_json": ["POLICY_SET_CHANGED"],
            "ignored_reason_codes_json": ["POLICY_VERSION_CHANGED"],
            "interpretation_rules_json": {
                "severity_increase_band": "attention",
                "review_required_flip_band": "critical_review",
                "watched_reason_code_band": "review_required",
                "ignored_reason_codes_do_not_affect_band": True,
            },
            "default_interpretation_band": "stable",
        },
    )
    assert create.status_code == 201
    preset = create.json()

    listed = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
    )
    assert listed.status_code == 200
    assert any(item["id"] == preset["id"] for item in listed.json())

    update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=headers,
        json={"description": "updated", "status": "inactive"},
    )
    assert update.status_code == 200
    assert update.json()["description"] == "updated"
    assert update.json()["status"] == "inactive"

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    archived_update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset['id']}",
        headers=headers,
        json={"name": "should fail"},
    )
    assert archived_update.status_code == 400


def test_phase516_preset_evaluate_interpretation_and_no_persist_no_audit(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p516-eval")
    headers = org["org_headers"]

    diff_id = _create_diff_report(client, headers)
    profile_id = _create_profile(client, headers)

    baseline = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=2,
        reason_code_classifications=[
            {"reason_code": "POLICY_VERSION_CHANGED", "count": 2, "severity": "low", "review_required": False},
        ],
    )
    compare_primary = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="critical",
        review_required=True,
        reason_code_count=2,
        reason_code_classifications=[
            {"reason_code": "POLICY_SET_CHANGED", "count": 1, "severity": "high", "review_required": True},
            {"reason_code": "POLICY_VERSION_CHANGED", "count": 1, "severity": "low", "review_required": False},
        ],
    )
    compare_ignored_only = _insert_gating_report(
        db_session,
        organization_id=org["organization_id"],
        diff_report_id=diff_id,
        profile_id=profile_id,
        max_severity="low",
        review_required=False,
        reason_code_count=4,
        reason_code_classifications=[
            {"reason_code": "POLICY_VERSION_CHANGED", "count": 4, "severity": "low", "review_required": False},
        ],
    )

    create_preset = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=headers,
        json={
            "name": "P516 Eval Preset",
            "baseline_gating_report_id": baseline,
            "baseline_gating_profile_id": profile_id,
            "watched_reason_codes_json": ["POLICY_SET_CHANGED"],
            "ignored_reason_codes_json": ["POLICY_VERSION_CHANGED"],
            "interpretation_rules_json": {
                "severity_increase_band": "attention",
                "review_required_flip_band": "critical_review",
                "watched_reason_code_band": "review_required",
                "ignored_reason_codes_do_not_affect_band": True,
            },
            "default_interpretation_band": "stable",
        },
    )
    assert create_preset.status_code == 201
    preset_id = create_preset.json()["id"]

    preview = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/evaluate",
        headers=headers,
        json={"compare_gating_report_id": compare_primary, "persist_report": False},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["persisted"] is False
    assert preview_body["preset_report_id"] is None
    assert preview_body["base_gating_report_id"] == baseline
    assert preview_body["compare_gating_report_id"] == compare_primary
    assert preview_body["interpretation_band"] == "critical_review"
    assert preview_body["review_required"] is True
    assert preview_body["watched_reason_codes_hit_count"] >= 1
    assert preview_body["ignored_reason_codes_hit_count"] >= 1
    assert "review_required_flip_band" in preview_body["matched_rules"]
    assert "watched_reason_code_band" in preview_body["matched_rules"]

    override = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/evaluate",
        headers=headers,
        json={
            "base_gating_report_id": baseline,
            "compare_gating_report_id": compare_ignored_only,
            "persist_report": False,
        },
    )
    assert override.status_code == 200
    override_body = override.json()
    assert override_body["base_gating_report_id"] == baseline
    assert override_body["compare_gating_report_id"] == compare_ignored_only
    assert override_body["interpretation_band"] == "stable"
    assert override_body["review_required"] is False
    assert override_body["ignored_reason_codes_hit_count"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare_preset_report.generated" not in actions


def test_phase516_preset_report_persistence_tenant_scope_summary_and_audit(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p516-persist-1")
    org2 = bootstrap_org_user(client, email_prefix="p516-persist-2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    diff1 = _create_diff_report(client, h1)
    profile1 = _create_profile(client, h1)
    base1 = _insert_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        diff_report_id=diff1,
        profile_id=profile1,
        max_severity="low",
        review_required=False,
        reason_code_count=1,
        reason_code_classifications=[{"reason_code": "CONTEXT_UNCHANGED", "count": 1, "severity": "info", "review_required": False}],
    )
    compare1 = _insert_gating_report(
        db_session,
        organization_id=org1["organization_id"],
        diff_report_id=diff1,
        profile_id=profile1,
        max_severity="high",
        review_required=True,
        reason_code_count=2,
        reason_code_classifications=[
            {"reason_code": "POLICY_SET_CHANGED", "count": 1, "severity": "high", "review_required": True},
            {"reason_code": "CONTEXT_ADDED", "count": 1, "severity": "low", "review_required": False},
        ],
    )

    preset = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets",
        headers=h1,
        json={
            "name": "P516 Persist Preset",
            "baseline_gating_report_id": base1,
            "baseline_gating_profile_id": profile1,
            "watched_reason_codes_json": ["POLICY_SET_CHANGED"],
            "ignored_reason_codes_json": [],
            "interpretation_rules_json": {
                "severity_increase_band": "attention",
                "review_required_flip_band": "critical_review",
                "watched_reason_code_band": "review_required",
            },
            "default_interpretation_band": "stable",
        },
    )
    assert preset.status_code == 201
    preset_id = preset.json()["id"]

    persisted = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_id}/evaluate",
        headers=h1,
        json={
            "compare_gating_report_id": compare1,
            "persist_report": True,
            "persist_compare_report": True,
        },
    )
    assert persisted.status_code == 200
    body = persisted.json()
    assert body["persisted"] is True
    assert body["preset_report_id"] is not None
    assert body["compare_report_id"] is not None
    assert body["interpretation_band"] in {"review_required", "critical_review"}
    assert body["review_required"] is True

    list_reports = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports"
        "?interpretation_band=review_required&review_required=true",
        headers=h1,
    )
    assert list_reports.status_code == 200
    list_reports_other = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports",
        headers=h2,
    )
    assert list_reports_other.status_code == 200
    assert all(item["id"] != body["preset_report_id"] for item in list_reports_other.json())

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{body['preset_report_id']}",
        headers=h1,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == body["preset_report_id"]

    cross_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{body['preset_report_id']}",
        headers=h2,
    )
    assert cross_detail.status_code == 404

    archive = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{body['preset_report_id']}/archive",
        headers=h1,
        json={"reason": "done"},
    )
    assert archive.status_code == 200
    assert archive.json()["status"] == "archived"

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-summary",
        headers=h1,
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["active_presets"] >= 1
    assert summary_body["total_preset_reports"] >= 1
    assert summary_body["archived_preset_reports"] >= 1
    assert summary_body["review_required_reports"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare_preset.created" in actions
    assert "ai_system_governance_policy_diff_gating_compare.generated" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset_report.generated" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset_report.archived" in actions
