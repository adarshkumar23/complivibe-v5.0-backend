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


def _policy_profile(ack_text: str) -> dict:
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


def _create_policy_set_with_active_version(client, headers: dict[str, str], *, name: str, ack_text: str) -> dict:
    policy_set = client.post(
        "/api/v1/ai-governance/guardrails/policy-sets",
        headers=headers,
        json={"name": name},
    )
    assert policy_set.status_code == 201
    policy_set_body = policy_set.json()

    version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_set_body['id']}/versions",
        headers=headers,
        json={"profile_json": _policy_profile(ack_text), "change_reason": "create"},
    )
    assert version.status_code == 201
    version_body = version.json()

    activated = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{policy_set_body['id']}/versions/{version_body['id']}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activated.status_code == 200

    return {"policy_set": policy_set_body, "version": version_body}


def _create_assignment(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post("/api/v1/ai-governance/guardrails/policy-assignments", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase510_policy_assignment_crud_history_summary_and_audit(client):
    org = bootstrap_org_user(client, email_prefix="p510-crud")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P510 AI")
    pack = _create_pack_with_step(client, headers, name="P510 Pack")
    policy = _create_policy_set_with_active_version(client, headers, name="P510 Profile", ack_text="ACK_P510")

    missing_reason = client.post(
        "/api/v1/ai-governance/guardrails/policy-assignments",
        headers=headers,
        json={
            "policy_set_id": policy["policy_set"]["id"],
            "scope_type": "all_ai_governance",
        },
    )
    assert missing_reason.status_code == 422

    invalid_scope = client.post(
        "/api/v1/ai-governance/guardrails/policy-assignments",
        headers=headers,
        json={
            "policy_set_id": policy["policy_set"]["id"],
            "scope_type": "unknown_scope",
            "reason": "x",
        },
    )
    assert invalid_scope.status_code == 422

    created = _create_assignment(
        client,
        headers,
        {
            "policy_set_id": policy["policy_set"]["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack["id"],
            "reason": "pack default",
            "priority": 150,
        },
    )

    duplicate = client.post(
        "/api/v1/ai-governance/guardrails/policy-assignments",
        headers=headers,
        json={
            "policy_set_id": policy["policy_set"]["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack["id"],
            "reason": "dup",
            "priority": 120,
        },
    )
    assert duplicate.status_code == 400

    list_response = client.get("/api/v1/ai-governance/guardrails/policy-assignments", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == created["id"] for item in list_response.json())

    updated = client.patch(
        f"/api/v1/ai-governance/guardrails/policy-assignments/{created['id']}",
        headers=headers,
        json={"priority": 300, "reason": "raise priority"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 300

    history_after_update = client.get(
        f"/api/v1/ai-governance/guardrails/policy-assignments/{created['id']}/history",
        headers=headers,
    )
    assert history_after_update.status_code == 200
    assert len(history_after_update.json()) == 2

    archive_missing_reason = client.post(
        f"/api/v1/ai-governance/guardrails/policy-assignments/{created['id']}/archive",
        headers=headers,
        json={},
    )
    assert archive_missing_reason.status_code == 422

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-assignments/{created['id']}/archive",
        headers=headers,
        json={"reason": "retire"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary = client.get("/api/v1/ai-governance/guardrails/policy-assignments/summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["archived_assignments"] >= 1
    assert summary_body["highest_priority"] >= 300

    history = client.get(
        f"/api/v1/ai-governance/guardrails/policy-assignments/{created['id']}/history",
        headers=headers,
    )
    assert history.status_code == 200
    assert [row["event_type"] for row in history.json()[:3]] == ["archived", "updated", "created"]

    # Keep cross-scope validation explicit.
    ai_scope = _create_assignment(
        client,
        headers,
        {
            "policy_set_id": policy["policy_set"]["id"],
            "scope_type": "ai_system",
            "scope_id": ai["id"],
            "reason": "ai specific",
        },
    )
    assert ai_scope["scope_type"] == "ai_system"

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_guardrail_policy_assignment.created" in actions
    assert "ai_system_governance_guardrail_policy_assignment.updated" in actions
    assert "ai_system_governance_guardrail_policy_assignment.archived" in actions


def test_phase510_policy_resolution_precedence_and_explicit_override(client):
    org = bootstrap_org_user(client, email_prefix="p510-resolution")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P510 Resolve AI")
    pack = _create_pack_with_step(client, headers, name="P510 Resolve Pack")

    global_policy = _create_policy_set_with_active_version(client, headers, name="Global", ack_text="ACK_GLOBAL")
    sequence_policy = _create_policy_set_with_active_version(client, headers, name="Seq", ack_text="ACK_SEQUENCE")
    explicit_policy = _create_policy_set_with_active_version(client, headers, name="Explicit", ack_text="ACK_EXPLICIT")

    _create_assignment(
        client,
        headers,
        {
            "policy_set_id": global_policy["policy_set"]["id"],
            "scope_type": "all_ai_governance",
            "reason": "global default",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "policy_set_id": sequence_policy["policy_set"]["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack["id"],
            "reason": "pack default",
            "priority": 120,
        },
    )

    resolved = client.post(
        "/api/v1/ai-governance/guardrails/policy-assignments/resolve",
        headers=headers,
        json={
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "rollout_class": "standard",
        },
    )
    assert resolved.status_code == 200
    resolved_body = resolved.json()
    assert resolved_body["resolved_policy_set_id"] == sequence_policy["policy_set"]["id"]
    assert resolved_body["resolution_source"] == "mapped_sequence_pack"

    explicit_resolved = client.post(
        "/api/v1/ai-governance/guardrails/policy-assignments/resolve",
        headers=headers,
        json={
            "explicit_policy_set_id": explicit_policy["policy_set"]["id"],
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
        },
    )
    assert explicit_resolved.status_code == 200
    explicit_body = explicit_resolved.json()
    assert explicit_body["resolved_policy_set_id"] == explicit_policy["policy_set"]["id"]
    assert explicit_body["resolution_source"] == "explicit_request"



def test_phase510_check_resolve_and_sequence_use_mapped_defaults_with_explicit_precedence(client):
    org = bootstrap_org_user(client, email_prefix="p510-integration")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P510 Seq AI")
    pack = _create_pack_with_step(client, headers, name="P510 Seq Pack")

    ai_policy = _create_policy_set_with_active_version(client, headers, name="AI Policy", ack_text="ACK_AI")
    review_policy = _create_policy_set_with_active_version(client, headers, name="Review Policy", ack_text="ACK_REVIEW")
    explicit_policy = _create_policy_set_with_active_version(client, headers, name="Explicit Policy", ack_text="ACK_EXPLICIT")

    _create_assignment(
        client,
        headers,
        {
            "policy_set_id": review_policy["policy_set"]["id"],
            "scope_type": "review_type",
            "scope_json": {"review_type": "initial_review"},
            "reason": "review fallback",
        },
    )
    _create_assignment(
        client,
        headers,
        {
            "policy_set_id": ai_policy["policy_set"]["id"],
            "scope_type": "ai_system",
            "scope_id": ai["id"],
            "reason": "ai specific",
            "priority": 200,
        },
    )

    now = datetime.now(UTC).replace(microsecond=0)
    freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "P510 freeze",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "freeze",
            "enforcement_level": "block",
            "override_allowed": True,
        },
    )
    assert freeze.status_code == 201

    check = client.post(
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
    assert check.status_code == 200
    check_body = check.json()
    assert check_body["policy_resolution"]["resolution_source"] == "mapped_ai_system"
    assert check_body["required_acknowledgement_text"] == "ACK_AI"

    resolve_conflicts = client.post(
        "/api/v1/ai-governance/guardrails/resolve-conflicts",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=1)).isoformat(),
            "rollout_class": "canary",
        },
    )
    assert resolve_conflicts.status_code == 200
    assert resolve_conflicts.json()["policy_resolution"]["resolution_source"] == "mapped_ai_system"

    mapped_apply = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "acknowledgement_text": "ACK_AI",
            "override_freeze": True,
            "override_reason": "approved",
            "rollout_class": "canary",
        },
    )
    assert mapped_apply.status_code == 200
    mapped_body = mapped_apply.json()
    assert mapped_body["guardrail_results"]["policy_resolution"]["resolution_source"] == "mapped_ai_system"

    explicit_apply_wrong_ack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "guardrail_policy_set_id": explicit_policy["policy_set"]["id"],
            "acknowledgement_text": "ACK_AI",
            "override_freeze": True,
            "override_reason": "attempt",
        },
    )
    assert explicit_apply_wrong_ack.status_code == 400

    explicit_apply = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "guardrail_policy_set_id": explicit_policy["policy_set"]["id"],
            "acknowledgement_text": "ACK_EXPLICIT",
            "override_freeze": True,
            "override_reason": "approved explicit",
        },
    )
    assert explicit_apply.status_code == 200
    assert explicit_apply.json()["guardrail_results"]["policy_resolution"]["resolution_source"] == "explicit_request"



def test_phase510_mapped_policy_without_active_version_is_rejected(client):
    org = bootstrap_org_user(client, email_prefix="p510-no-active")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P510 Missing Active AI")
    pack = _create_pack_with_step(client, headers, name="P510 Missing Active Pack")

    inactive_policy_set = client.post(
        "/api/v1/ai-governance/guardrails/policy-sets",
        headers=headers,
        json={"name": "No Active Version"},
    )
    assert inactive_policy_set.status_code == 201

    assignment = client.post(
        "/api/v1/ai-governance/guardrails/policy-assignments",
        headers=headers,
        json={
            "policy_set_id": inactive_policy_set.json()["id"],
            "scope_type": "all_ai_governance",
            "reason": "default without active version",
        },
    )
    assert assignment.status_code == 201

    now = datetime.now(UTC).replace(microsecond=0)
    check = client.post(
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
    assert check.status_code == 400

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
        },
    )
    assert resolve.status_code == 400

    sequence = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={"dry_run": True, "ai_system_ids": [ai["id"]], "start_from": now.isoformat()},
    )
    assert sequence.status_code == 400
