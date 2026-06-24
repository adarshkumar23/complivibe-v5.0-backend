from tests.helpers.auth_org import bootstrap_org_user
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_preset_versions_phase517 import _create_preset
from tests.unit.test_ai_system_governance_policy_diff_gating_compare_presets_phase516 import (
    _create_ai_system,
    _create_diff_report,
    _create_pack,
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


def test_phase519_preset_assignment_crud_validation_history_and_summary(client, db_session):
    org1 = bootstrap_org_user(client, email_prefix="p519-crud-1")
    org2 = bootstrap_org_user(client, email_prefix="p519-crud-2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    profile_id, base_id, _ = _create_context(client, db_session, h1, org1["organization_id"])
    preset = _create_preset(client, h1, baseline_report_id=base_id, profile_id=profile_id)
    pack1 = _create_pack(client, h1, name="P519 Pack1")
    pack2 = _create_pack(client, h2, name="P519 Pack2")
    ai1 = _create_ai_system(client, h1, name="P519 AI1")
    ai2 = _create_ai_system(client, h2, name="P519 AI2")

    missing_reason = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={"preset_id": preset["id"], "scope_type": "all_ai_governance"},
    )
    assert missing_reason.status_code == 422

    invalid_scope = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={"preset_id": preset["id"], "scope_type": "bad_scope", "reason": "x"},
    )
    assert invalid_scope.status_code == 422

    bad_seq_scope = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={
            "preset_id": preset["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack2["id"],
            "reason": "bad",
        },
    )
    assert bad_seq_scope.status_code == 404

    bad_ai_scope = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={
            "preset_id": preset["id"],
            "scope_type": "ai_system",
            "scope_id": ai2["id"],
            "reason": "bad",
        },
    )
    assert bad_ai_scope.status_code == 404

    bad_review_type = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={
            "preset_id": preset["id"],
            "scope_type": "review_type",
            "scope_json": {"review_type": "invalid"},
            "reason": "bad",
        },
    )
    assert bad_review_type.status_code == 400

    bad_rollout_class = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={
            "preset_id": preset["id"],
            "scope_type": "rollout_class",
            "scope_json": {},
            "reason": "bad",
        },
    )
    assert bad_rollout_class.status_code == 400

    create = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={
            "preset_id": preset["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack1["id"],
            "priority": 250,
            "reason": "assign pack",
            "status": "active",
        },
    )
    assert create.status_code == 201
    assignment = create.json()

    duplicate = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
        json={
            "preset_id": preset["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack1["id"],
            "reason": "duplicate",
        },
    )
    assert duplicate.status_code == 400

    list_self = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h1,
    )
    assert list_self.status_code == 200
    assert any(item["id"] == assignment["id"] for item in list_self.json())

    list_other = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=h2,
    )
    assert list_other.status_code == 200
    assert all(item["id"] != assignment["id"] for item in list_other.json())

    update = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment['id']}",
        headers=h1,
        json={
            "scope_type": "ai_system",
            "scope_id": ai1["id"],
            "priority": 300,
            "reason": "move to ai scope",
        },
    )
    assert update.status_code == 200
    assert update.json()["scope_type"] == "ai_system"
    assert update.json()["scope_id"] == ai1["id"]
    assert update.json()["priority"] == 300

    missing_archive_reason = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment['id']}/archive",
        headers=h1,
        json={},
    )
    assert missing_archive_reason.status_code == 422

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment['id']}/archive",
        headers=h1,
        json={"reason": "retire assignment"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    history = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/{assignment['id']}/history",
        headers=h1,
    )
    assert history.status_code == 200
    events = [item["event_type"] for item in history.json()]
    assert "created" in events
    assert "updated" in events
    assert "archived" in events

    summary = client.get(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/summary",
        headers=h1,
    )
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["archived_assignments"] >= 1
    assert summary_body["highest_priority"] >= 300

    logs = client.get("/api/v1/audit-logs", headers=h1)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_diff_gating_compare_preset_assignment.created" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset_assignment.updated" in actions
    assert "ai_system_governance_policy_diff_gating_compare_preset_assignment.archived" in actions


def test_phase519_preset_assignment_resolution_precedence_and_errors(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p519-resolve")
    headers = org["org_headers"]

    profile_id, base_id, _ = _create_context(client, db_session, headers, org["organization_id"])
    preset_global = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_sequence = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_ai = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    preset_explicit = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    pack = _create_pack(client, headers, name="P519 Resolve Pack")
    ai_system = _create_ai_system(client, headers, name="P519 Resolve AI")

    for payload in [
        {
            "preset_id": preset_global["id"],
            "scope_type": "all_ai_governance",
            "reason": "global",
            "priority": 100,
        },
        {
            "preset_id": preset_global["id"],
            "scope_type": "review_type",
            "scope_json": {"review_type": "initial_review"},
            "reason": "review-type",
            "priority": 90,
        },
        {
            "preset_id": preset_global["id"],
            "scope_type": "rollout_class",
            "scope_json": {"rollout_class": "standard"},
            "reason": "rollout-class",
            "priority": 80,
        },
        {
            "preset_id": preset_sequence["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack["id"],
            "reason": "sequence",
            "priority": 120,
        },
        {
            "preset_id": preset_ai["id"],
            "scope_type": "ai_system",
            "scope_id": ai_system["id"],
            "reason": "ai",
            "priority": 110,
        },
    ]:
        created = client.post(
            "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
            headers=headers,
            json=payload,
        )
        assert created.status_code == 201

    ai_wins = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve",
        headers=headers,
        json={
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai_system["id"]],
            "review_types": ["initial_review"],
            "rollout_class": "standard",
        },
    )
    assert ai_wins.status_code == 200
    ai_body = ai_wins.json()
    assert ai_body["resolved_preset_id"] == preset_sequence["id"] or ai_body["resolved_preset_id"] == preset_ai["id"]
    # Per precedence: sequence_pack before ai_system.
    assert ai_body["resolved_preset_id"] == preset_sequence["id"]
    assert ai_body["resolution_source"] == "mapped_sequence_pack"
    assert isinstance(ai_body["precedence_trace"], list)

    ai_scope_wins = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve",
        headers=headers,
        json={
            "ai_system_ids": [ai_system["id"]],
            "review_types": ["initial_review"],
            "rollout_class": "standard",
        },
    )
    assert ai_scope_wins.status_code == 200
    assert ai_scope_wins.json()["resolved_preset_id"] == preset_ai["id"]
    assert ai_scope_wins.json()["resolution_source"] == "mapped_ai_system"

    explicit = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve",
        headers=headers,
        json={
            "explicit_preset_id": preset_explicit["id"],
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai_system["id"]],
        },
    )
    assert explicit.status_code == 200
    assert explicit.json()["resolved_preset_id"] == preset_explicit["id"]
    assert explicit.json()["resolution_source"] == "explicit_request"

    make_sequence_inactive = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_sequence['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert make_sequence_inactive.status_code == 200
    inactive_err = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve",
        headers=headers,
        json={"sequence_pack_id": pack["id"]},
    )
    assert inactive_err.status_code == 400

    make_sequence_archived = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{preset_sequence['id']}",
        headers=headers,
        json={"status": "archived"},
    )
    assert make_sequence_archived.status_code == 200
    archived_err = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments/resolve",
        headers=headers,
        json={"sequence_pack_id": pack["id"]},
    )
    assert archived_err.status_code == 400


def test_phase519_evaluate_default_resolution_pinning_and_persisted_resolution(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p519-eval-default")
    headers = org["org_headers"]

    profile_id, base_id, compare_id = _create_context(client, db_session, headers, org["organization_id"])
    mapped_preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)
    explicit_preset = _create_preset(client, headers, baseline_report_id=base_id, profile_id=profile_id)

    mapped_v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{mapped_preset['id']}/versions",
        headers=headers,
        json={"change_reason": "mapped-v1"},
    )
    assert mapped_v1.status_code == 201
    pin = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{mapped_preset['id']}/pin-version",
        headers=headers,
        json={
            "version_id": mapped_v1.json()["id"],
            "version_selection_mode": "pinned_required",
            "allow_explicit_version_override": False,
            "reason": "lock mapped",
        },
    )
    assert pin.status_code == 200

    global_assignment = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-assignments",
        headers=headers,
        json={
            "preset_id": mapped_preset["id"],
            "scope_type": "all_ai_governance",
            "reason": "default mapped",
        },
    )
    assert global_assignment.status_code == 201

    default_eval = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default",
        headers=headers,
        json={"compare_gating_report_id": compare_id},
    )
    assert default_eval.status_code == 200
    body = default_eval.json()
    assert body["preset_id"] == mapped_preset["id"]
    assert body["preset_resolution"]["resolution_source"] == "mapped_all_ai_governance"
    assert body["version_resolution_source"] == "pinned_version"
    assert body["pinned_version_id"] == mapped_v1.json()["id"]

    explicit_eval = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default",
        headers=headers,
        json={
            "explicit_preset_id": explicit_preset["id"],
            "compare_gating_report_id": compare_id,
        },
    )
    assert explicit_eval.status_code == 200
    explicit_body = explicit_eval.json()
    assert explicit_body["preset_id"] == explicit_preset["id"]
    assert explicit_body["preset_resolution"]["resolution_source"] == "explicit_request"

    persisted = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default",
        headers=headers,
        json={"compare_gating_report_id": compare_id, "persist_report": True},
    )
    assert persisted.status_code == 200
    persisted_body = persisted.json()
    assert persisted_body["persisted"] is True
    report_id = persisted_body["preset_report_id"]
    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-preset-reports/{report_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert "preset_resolution" in detail.json()["result_json"]
    assert detail.json()["result_json"]["preset_resolution"]["resolution_source"] == "mapped_all_ai_governance"

    make_mapped_inactive = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/{mapped_preset['id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert make_mapped_inactive.status_code == 200
    inactive_eval = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/diff-gating-compare-presets/evaluate-default",
        headers=headers,
        json={"compare_gating_report_id": compare_id},
    )
    assert inactive_eval.status_code == 400
