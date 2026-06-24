import uuid
from datetime import UTC, datetime, timedelta

from app.models.ai_system_governance_operator_acknowledgement import AISystemGovernanceOperatorAcknowledgement
from tests.helpers.auth_org import bootstrap_org_user


def _create_ai_system(client, headers: dict[str, str], *, name: str) -> dict:
    response = client.post(
        "/api/v1/ai-systems",
        headers=headers,
        json={"name": name, "system_type": "agent"},
    )
    assert response.status_code == 201
    return response.json()


def _create_pack(client, headers: dict[str, str], *, name: str = "P58 Pack") -> dict:
    response = client.post(
        "/api/v1/ai-governance/review-sequence-packs",
        headers=headers,
        json={"name": name, "status": "active"},
    )
    assert response.status_code == 201
    return response.json()


def _create_step(client, headers: dict[str, str], pack_id: str, *, step_order: int = 1) -> dict:
    response = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack_id}/steps",
        headers=headers,
        json={"step_order": step_order, "review_type": "initial_review", "offset_days_from_start": 0},
    )
    assert response.status_code == 201
    return response.json()


def _create_freeze(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post("/api/v1/ai-governance/guardrails/freeze-windows", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase58_freeze_window_fields_validation_and_audit(client):
    org = bootstrap_org_user(client, email_prefix="p58-fields")
    headers = org["org_headers"]
    now = datetime.now(UTC).replace(microsecond=0)

    invalid_enforcement = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "Invalid enforcement",
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "reason": "x",
            "enforcement_level": "hard_block",
        },
    )
    assert invalid_enforcement.status_code == 422

    negative_priority = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "Negative priority",
            "starts_at": now.isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "reason": "x",
            "priority": -1,
        },
    )
    assert negative_priority.status_code == 422

    created = _create_freeze(
        client,
        headers,
        {
            "name": "P58 explicit",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "reason": "release hold",
            "priority": 250,
            "enforcement_level": "warn",
            "override_allowed": False,
            "precedence_notes": "critical scope",
        },
    )
    assert created["priority"] == 250
    assert created["enforcement_level"] == "warn"
    assert created["override_allowed"] is False
    assert created["precedence_notes"] == "critical scope"

    updated = client.patch(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{created['id']}",
        headers=headers,
        json={"priority": 300, "enforcement_level": "block", "override_allowed": True, "precedence_notes": "updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 300
    assert updated.json()["enforcement_level"] == "block"
    assert updated.json()["override_allowed"] is True
    assert updated.json()["precedence_notes"] == "updated"

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{created['id']}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archived.status_code == 200

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_freeze_window.created" in actions
    assert "ai_system_governance_freeze_window.updated" in actions
    assert "ai_system_governance_freeze_window.archived" in actions


def test_phase58_guardrail_precedence_resolution_preview_and_summary(client):
    org = bootstrap_org_user(client, email_prefix="p58-resolution")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P58 AI")
    pack = _create_pack(client, headers, name="P58 Pack")
    _create_step(client, headers, pack["id"])

    now = datetime.now(UTC).replace(microsecond=0)

    all_warn_1 = _create_freeze(
        client,
        headers,
        {
            "name": "All warn A",
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "all warn a",
            "priority": 100,
            "enforcement_level": "warn",
        },
    )
    all_warn_2 = _create_freeze(
        client,
        headers,
        {
            "name": "All warn B",
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "all warn b",
            "priority": 100,
            "enforcement_level": "warn",
        },
    )
    review_info = _create_freeze(
        client,
        headers,
        {
            "name": "Review info",
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2)).isoformat(),
            "scope_type": "review_type",
            "scope_json": {"review_types": ["initial_review"]},
            "reason": "review info",
            "priority": 100,
            "enforcement_level": "info",
        },
    )
    pack_warn = _create_freeze(
        client,
        headers,
        {
            "name": "Pack warn",
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2)).isoformat(),
            "scope_type": "sequence_pack",
            "scope_json": {"sequence_pack_ids": [pack["id"]]},
            "reason": "pack warn",
            "priority": 100,
            "enforcement_level": "warn",
        },
    )
    ai_warn = _create_freeze(
        client,
        headers,
        {
            "name": "AI warn",
            "starts_at": (now - timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2)).isoformat(),
            "scope_type": "ai_system",
            "scope_json": {"ai_system_ids": [ai["id"]]},
            "reason": "ai warn",
            "priority": 100,
            "enforcement_level": "warn",
        },
    )

    check_warn_info = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert check_warn_info.status_code == 200
    body = check_warn_info.json()
    assert body["blocked"] is False
    assert body["resolution"]["blocked"] is False
    assert body["resolution"]["enforcement_level"] == "warn"
    assert body["required_acknowledgement_text"] is None

    ordered_ids = [item["id"] for item in body["matching_freeze_windows"]]
    assert ordered_ids[0] == ai_warn["id"]
    assert ordered_ids[1] == pack_warn["id"]
    assert ordered_ids[2] == review_info["id"]
    all_ids_in_order = [item for item in ordered_ids if item in {all_warn_1["id"], all_warn_2["id"]}]
    assert all_ids_in_order == sorted(all_ids_in_order)

    preview = client.post(
        "/api/v1/ai-governance/guardrails/resolve-conflicts",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["sorted_precedence_order"] == body["resolution"]["precedence_order"]
    assert preview_body["final_decision"]["blocked"] is False
    assert preview_body["explanation"]

    high_priority_block = _create_freeze(
        client,
        headers,
        {
            "name": "Global high block",
            "starts_at": (now - timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "high block",
            "priority": 999,
            "enforcement_level": "block",
            "override_allowed": False,
        },
    )

    check_block = client.post(
        "/api/v1/ai-governance/guardrails/check",
        headers=headers,
        json={
            "action_type": "sequence_apply",
            "sequence_pack_id": pack["id"],
            "ai_system_ids": [ai["id"]],
            "review_types": ["initial_review"],
            "planned_start": now.isoformat(),
            "planned_end": (now + timedelta(hours=2)).isoformat(),
        },
    )
    assert check_block.status_code == 200
    block_body = check_block.json()
    assert block_body["blocked"] is True
    assert block_body["resolution"]["primary_blocking_window_id"] == high_priority_block["id"]
    assert block_body["resolution"]["override_allowed"] is False
    assert block_body["required_acknowledgement_text"] is None

    summary = client.get("/api/v1/ai-governance/guardrails/summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["block_freeze_windows"] == 1
    assert summary_body["warn_freeze_windows"] >= 4
    assert summary_body["info_freeze_windows"] == 1
    assert summary_body["override_disallowed_windows"] == 1
    assert summary_body["highest_priority"] == 999


def test_phase58_sequence_apply_uses_resolved_override_rules(client, db_session):
    org = bootstrap_org_user(client, email_prefix="p58-seq")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P58 Sequence AI")
    pack = _create_pack(client, headers, name="P58 Sequence Pack")
    _create_step(client, headers, pack["id"])

    now = datetime.now(UTC).replace(microsecond=0)

    freeze = _create_freeze(
        client,
        headers,
        {
            "name": "No override block",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "strict freeze",
            "priority": 500,
            "enforcement_level": "block",
            "override_allowed": False,
        },
    )

    denied_even_with_ack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "acknowledgement_text": "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE",
            "override_freeze": True,
            "override_reason": "trying override",
        },
    )
    assert denied_even_with_ack.status_code == 400

    enable_override = client.patch(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{freeze['id']}",
        headers=headers,
        json={"override_allowed": True},
    )
    assert enable_override.status_code == 200

    allowed_with_ack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={
            "dry_run": False,
            "ai_system_ids": [ai["id"]],
            "start_from": now.isoformat(),
            "acknowledgement_text": "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE",
            "override_freeze": True,
            "override_reason": "manual approval",
        },
    )
    assert allowed_with_ack.status_code == 200
    assert allowed_with_ack.json()["created_count"] >= 1

    ack_rows = (
        db_session.query(AISystemGovernanceOperatorAcknowledgement)
        .filter(AISystemGovernanceOperatorAcknowledgement.organization_id == uuid.UUID(org["organization_id"]))
        .all()
    )
    assert len(ack_rows) == 1

    set_warn = client.patch(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{freeze['id']}",
        headers=headers,
        json={"enforcement_level": "warn"},
    )
    assert set_warn.status_code == 200

    warn_apply_without_ack = client.post(
        f"/api/v1/ai-governance/review-sequence-packs/{pack['id']}/generate-sequence",
        headers=headers,
        json={"dry_run": True, "ai_system_ids": [ai["id"]], "start_from": now.isoformat()},
    )
    assert warn_apply_without_ack.status_code == 200
    warn_body = warn_apply_without_ack.json()
    assert warn_body["guardrail_results"]["blocked"] is False
    assert warn_body["guardrail_results"]["resolution"]["enforcement_level"] == "warn"

    set_info = client.patch(
        f"/api/v1/ai-governance/guardrails/freeze-windows/{freeze['id']}",
        headers=headers,
        json={"enforcement_level": "info"},
    )
    assert set_info.status_code == 200

    info_check = client.post(
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
    assert info_check.status_code == 200
    assert info_check.json()["blocked"] is False
    assert info_check.json()["resolution"]["enforcement_level"] == "info"
