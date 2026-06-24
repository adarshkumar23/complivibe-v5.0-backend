from datetime import UTC, datetime, timedelta

from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post("/api/v1/ai-systems", headers=headers, json={"name": name, "system_type": "agent"})
    assert response.status_code == 201
    return response.json()


def _create_pack_with_step(client, headers: dict[str, str], *, name: str) -> dict:
    pack = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert pack.status_code == 201
    step = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack.json()['id']}/steps",
        headers=headers,
        json={"step_order": 1, "review_type": "initial_review", "offset_days_from_start": 0},
    )
    assert step.status_code == 201
    return pack.json()


def _create_policy_set(client, headers: dict[str, str], *, name: str = "Policy Set") -> dict:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-sets",
        headers=headers,
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()


def _policy_profile(ack_text: str = "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE") -> dict:
    return {
        "resolution_strategy": "deterministic_precedence_v1",
        "acknowledgement_text": ack_text,
        "allow_operator_override": True,
        "require_override_reason": True,
        "include_info_windows": True,
        "include_warn_windows": True,
        "include_block_windows": True,
        "scope_precedence_order": ["ai_system", "sequence_pack", "review_type", "all_ai_governance"],
    }


def test_phase59_policy_set_crud_versions_activation_and_summary(client):
    org = bootstrap_org_user(client, email_prefix="p59-crud")
    headers = org["org_headers"]

    created = _create_policy_set(client, headers, name="Rollout Profile")

    listed = client.get("/api/v1/ai-governance/guardrails/policy-sets", headers=headers)
    assert listed.status_code == 200
    assert any(item["id"] == created["id"] for item in listed.json())

    updated = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}",
        headers=headers,
        json={"name": "Rollout Profile Updated", "status": "inactive"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Rollout Profile Updated"

    invalid_profile = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions",
        headers=headers,
        json={
            "profile_json": {
                "resolution_strategy": "deterministic_precedence_v1",
                "allow_operator_override": True,
                "scope_precedence_order": ["ai_system", "sequence_pack", "review_type", "all_ai_governance"],
            },
            "change_reason": "invalid",
        },
    )
    assert invalid_profile.status_code == 400

    v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions",
        headers=headers,
        json={"profile_json": _policy_profile("CONFIRM_P59_OVERRIDE"), "change_reason": "initial"},
    )
    assert v1.status_code == 201
    assert v1.json()["version_number"] == 1
    assert v1.json()["status"] == "draft"

    v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions",
        headers=headers,
        json={"profile_json": _policy_profile("CONFIRM_P59_OVERRIDE_V2"), "change_reason": "second"},
    )
    assert v2.status_code == 201
    assert v2.json()["version_number"] == 2

    versions = client.get(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions",
        headers=headers,
    )
    assert versions.status_code == 200
    assert [item["version_number"] for item in versions.json()[:2]] == [2, 1]

    activate_v1 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions/{v1.json()['id']}/activate",
        headers=headers,
        json={"reason": "go live v1"},
    )
    assert activate_v1.status_code == 200
    assert activate_v1.json()["status"] == "active"

    activate_v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions/{v2.json()['id']}/activate",
        headers=headers,
        json={"reason": "go live v2"},
    )
    assert activate_v2.status_code == 200
    assert activate_v2.json()["status"] == "active"

    versions_after = client.get(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions",
        headers=headers,
    )
    assert versions_after.status_code == 200
    statuses = {item["version_number"]: item["status"] for item in versions_after.json()}
    assert statuses[2] == "active"
    assert statuses[1] == "deprecated"

    active_profile = client.get(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/active-profile",
        headers=headers,
    )
    assert active_profile.status_code == 200
    assert active_profile.json()["version_number"] == 2
    assert "deterministic configuration records" in active_profile.json()["caveat"]

    summary = client.get("/api/v1/ai-governance/guardrails/policy-sets/summary", headers=headers)
    assert summary.status_code == 200
    body = summary.json()
    assert body["active_policy_sets"] == 0
    assert body["inactive_policy_sets"] == 1
    assert body["total_versions"] == 2
    assert body["active_versions"] == 1
    assert body["deprecated_versions"] == 1

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/archive",
        headers=headers,
        json={"reason": "retired"},
    )
    assert archived.status_code == 200

    blocked_new_version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{created['id']}/versions",
        headers=headers,
        json={"profile_json": _policy_profile(), "change_reason": "should fail"},
    )
    assert blocked_new_version.status_code == 400

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_guardrail_policy_set.created" in actions
    assert "ai_system_governance_guardrail_policy_set.updated" in actions
    assert "ai_system_governance_guardrail_policy_set.archived" in actions
    assert "ai_system_governance_guardrail_policy_set_version.created" in actions
    assert "ai_system_governance_guardrail_policy_set_version.activated" in actions


def test_phase59_guardrail_check_resolve_and_sequence_with_policy_profile(client):
    org = bootstrap_org_user(client, email_prefix="p59-behavior")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P59 AI")
    pack = _create_pack_with_step(client, headers, name="P59 Pack")

    now = datetime.now(UTC).replace(microsecond=0)

    freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "Blocking freeze",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "freeze",
            "enforcement_level": "block",
            "override_allowed": True,
        },
    )
    assert freeze.status_code == 201

    baseline_check = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert baseline_check.status_code == 200
    assert baseline_check.json()["blocked"] is True
    assert baseline_check.json()["required_acknowledgement_text"] == "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE"

    policy_set = _create_policy_set(client, headers, name="Custom Ack Profile")

    no_active_check = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
            "policy_set_id": policy_set["id"],
        },
    )
    assert no_active_check.status_code == 400

    version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_set['id']}/versions",
        headers=headers,
        json={"profile_json": _policy_profile("CONFIRM_CUSTOM_P59"), "change_reason": "custom ack"},
    )
    assert version.status_code == 201
    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_set['id']}/versions/{version.json()['id']}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activate.status_code == 200

    policy_check = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
            "policy_set_id": policy_set["id"],
        },
    )
    assert policy_check.status_code == 200
    policy_body = policy_check.json()
    assert policy_body["blocked"] is True
    assert policy_body["required_acknowledgement_text"] == "CONFIRM_CUSTOM_P59"
    assert policy_body["policy_set_id"] == policy_set["id"]
    assert policy_body["policy_version_id"] == version.json()["id"]

    resolve = client.post(
        "/api/v1/ai-governance/guardrails/resolve-conflicts",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
            "policy_set_id": policy_set["id"],
        },
    )
    assert resolve.status_code == 200
    assert resolve.json()["policy_set_id"] == policy_set["id"]
    assert resolve.json()["policy_version_id"] == version.json()["id"]

    wrong_ack_sequence = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "guardrail_policy_set_id": policy_set["id"],
            "acknowledgement_text": "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE",
            "override_freeze": True,
            "override_reason": "attempt",
        },
    )
    assert wrong_ack_sequence.status_code == 400

    ok_sequence = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "guardrail_policy_set_id": policy_set["id"],
            "acknowledgement_text": "CONFIRM_CUSTOM_P59",
            "override_freeze": True,
            "override_reason": "approved",
        },
    )
    assert ok_sequence.status_code == 200
    run_body = ok_sequence.json()
    assert run_body["created_count"] >= 1
    assert run_body["guardrail_results"]["policy_set_id"] == policy_set["id"]
    assert run_body["guardrail_results"]["policy_version_id"] == version.json()["id"]

    # Safety check: even profile filtering flags cannot bypass block decisions.
    v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_set['id']}/versions",
        headers=headers,
        json={
            "profile_json": {
                **_policy_profile("CONFIRM_CUSTOM_P59_V2"),
                "include_block_windows": False,
            },
            "change_reason": "hide blocks from display",
        },
    )
    assert v2.status_code == 201
    activate_v2 = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_set['id']}/versions/{v2.json()['id']}/activate",
        headers=headers,
        json={"reason": "activate v2"},
    )
    assert activate_v2.status_code == 200

    blocked_still = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
            "policy_set_id": policy_set["id"],
        },
    )
    assert blocked_still.status_code == 200
    assert blocked_still.json()["blocked"] is True
    assert blocked_still.json()["resolution"]["blocked"] is True
