from datetime import UTC, datetime, timedelta

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
    p = policy.json()

    version = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{p['id']}/versions",
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
    v = version.json()

    activate = client.post(
        f"/api/v1/ai-governance/guardrails/policy-sets/{p['id']}/versions/{v['id']}/activate",
        headers=headers,
        json={"reason": "activate"},
    )
    assert activate.status_code == 200
    return p


def _assign(client, headers: dict[str, str], payload: dict) -> None:
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


def _context_by_key(context_diffs: list[dict], key: str) -> dict:
    for item in context_diffs:
        if item.get("context_key") == key:
            return item
    raise AssertionError(f"missing context diff for key={key}")


def test_phase513_reason_code_catalog_endpoint_is_deterministic(client):
    org = bootstrap_org_user(client, email_prefix="p513-catalog")
    headers = org["org_headers"]

    first = client.get("/api/v1/ai-governance/guardrails/policy-resolution/diff-reason-codes", headers=headers)
    second = client.get("/api/v1/ai-governance/guardrails/policy-resolution/diff-reason-codes", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    codes = [item["code"] for item in first.json()["reason_codes"]]
    assert codes == sorted(codes)
    assert "CONTEXT_ADDED" in codes
    assert "POLICY_SET_CHANGED" in codes
    assert "GUARDRAIL_BLOCKED_CHANGED" in codes


def test_phase513_diff_reason_codes_field_changes_persist_and_summary(client):
    org = bootstrap_org_user(client, email_prefix="p513-diff")
    headers = org["org_headers"]

    ai_changed = _create_ai_system(client, headers, name="P513 AI Changed")
    ai_unchanged = _create_ai_system(client, headers, name="P513 AI Unchanged")
    pack = _create_pack(client, headers, name="P513 Pack")

    policy_mapped = _create_policy_set(client, headers, name="P513 Mapped", ack_text="ACK_M")
    policy_explicit = _create_policy_set(client, headers, name="P513 Explicit", ack_text="ACK_E")
    _assign(
        client,
        headers,
        {"policy_set_id": policy_mapped["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "pack"},
    )

    now = datetime.now(UTC).replace(microsecond=0)
    base_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-unchanged",
                "explicit_policy_set_id": policy_explicit["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai_unchanged["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            },
            {
                "context_key": "ctx-changed",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai_changed["id"]],
                "review_types": ["change_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=2)).isoformat(),
            },
            {
                "context_key": "ctx-removed",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai_changed["id"]],
                "review_types": ["periodic_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=3)).isoformat(),
            },
        ],
        title="base",
    )

    block = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "p513-block",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "ai_system",
            "scope_json": {"ai_system_ids": [ai_changed["id"]]},
            "reason": "block",
            "enforcement_level": "block",
            "override_allowed": False,
        },
    )
    assert block.status_code == 201
    warn = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "p513-warn",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "ai_system",
            "scope_json": {"ai_system_ids": [ai_changed["id"]]},
            "reason": "warn",
            "enforcement_level": "warn",
            "override_allowed": True,
        },
    )
    assert warn.status_code == 201
    info = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "p513-info",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "ai_system",
            "scope_json": {"ai_system_ids": [ai_changed["id"]]},
            "reason": "info",
            "enforcement_level": "info",
            "override_allowed": True,
        },
    )
    assert info.status_code == 201

    compare_report_id = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-unchanged",
                "explicit_policy_set_id": policy_explicit["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai_unchanged["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            },
            {
                "context_key": "ctx-changed",
                "explicit_policy_set_id": policy_explicit["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai_changed["id"]],
                "review_types": ["change_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=2)).isoformat(),
            },
            {
                "context_key": "ctx-added",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai_changed["id"]],
                "review_types": ["retirement_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=4)).isoformat(),
            },
            {
                "context_key": "ctx-no-policy",
                "ai_system_ids": [ai_changed["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=5)).isoformat(),
            },
        ],
        title="compare",
    )

    no_persist = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={
                "base_report_id": base_report_id,
                "compare_report_id": compare_report_id,
                "persist_diff": False,
                "context_match_strategy": "context_key_only",
            },
        )
    assert no_persist.status_code == 200
    no_persist_body = no_persist.json()
    assert no_persist_body["diff_report_id"] is None
    assert no_persist_body["reason_code_count"] > 0
    assert "CONTEXT_ADDED" in no_persist_body["reason_code_summary"]

    audit_logs = client.get("/api/v1/audit-logs", headers=headers)
    assert audit_logs.status_code == 200
    no_persist_actions = {item["action"] for item in audit_logs.json()}
    assert "ai_system_governance_policy_resolution_simulation_diff.generated" not in no_persist_actions

    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={
            "base_report_id": base_report_id,
            "compare_report_id": compare_report_id,
                "persist_diff": True,
                "title": "p513-diff",
                "context_match_strategy": "context_key_only",
            },
        )
    assert diff.status_code == 200
    body = diff.json()
    assert body["persisted"] is True
    assert body["diff_report_id"] is not None
    assert body["reason_code_count"] > 0
    assert body["reason_code_summary"]["CONTEXT_ADDED"] >= 1
    assert body["reason_code_summary"]["CONTEXT_REMOVED"] >= 1
    assert body["reason_code_summary"]["CONTEXT_UNCHANGED"] >= 1
    assert body["reason_code_summary"]["CONTEXT_CHANGED"] >= 1

    changed = _context_by_key(body["context_diffs"], "ctx-changed")
    added = _context_by_key(body["context_diffs"], "ctx-added")
    removed = _context_by_key(body["context_diffs"], "ctx-removed")
    unchanged = _context_by_key(body["context_diffs"], "ctx-unchanged")

    assert "CONTEXT_CHANGED" in changed["reason_codes"]
    assert "POLICY_RESOLUTION_SOURCE_CHANGED" in changed["reason_codes"]
    assert "POLICY_SET_CHANGED" in changed["reason_codes"]
    assert "POLICY_VERSION_CHANGED" in changed["reason_codes"]
    assert "POLICY_ASSIGNMENT_CHANGED" in changed["reason_codes"]
    assert "POLICY_PRECEDENCE_TRACE_CHANGED" in changed["reason_codes"]
    assert "GUARDRAIL_BLOCKED_CHANGED" in changed["reason_codes"]
    assert "PRIMARY_BLOCKING_WINDOW_CHANGED" in changed["reason_codes"]
    assert "GUARDRAIL_WARNINGS_CHANGED" in changed["reason_codes"]
    assert "GUARDRAIL_INFO_CHANGED" in changed["reason_codes"]

    changed_fields = {item["field_path"]: item for item in changed["field_changes"]}
    assert changed_fields["policy_resolution.resolution_source"]["reason_code"] == "POLICY_RESOLUTION_SOURCE_CHANGED"
    assert changed_fields["policy_resolution.resolved_policy_set_id"]["reason_code"] == "POLICY_SET_CHANGED"
    assert changed_fields["policy_resolution.resolved_policy_version_id"]["reason_code"] == "POLICY_VERSION_CHANGED"
    assert changed_fields["policy_resolution.assignment_id"]["reason_code"] == "POLICY_ASSIGNMENT_CHANGED"
    assert changed_fields["policy_resolution.precedence_trace"]["reason_code"] == "POLICY_PRECEDENCE_TRACE_CHANGED"
    assert changed_fields["guardrail_resolution.blocked"]["reason_code"] == "GUARDRAIL_BLOCKED_CHANGED"

    assert added["reason_codes"] == ["CONTEXT_ADDED"]
    assert removed["reason_codes"] == ["CONTEXT_REMOVED"]
    assert unchanged["reason_codes"] == ["CONTEXT_UNCHANGED"]

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{body['diff_report_id']}",
        headers=headers,
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["reason_code_count"] == body["reason_code_count"]
    assert detail_body["reason_code_summary_json"] == body["reason_code_summary"]

    summary = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-summary", headers=headers)
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total_reason_code_occurrences"] >= body["reason_code_count"]
    assert isinstance(summary_body["top_reason_codes"], list)
    assert summary_body["top_reason_codes"]

    top = summary_body["top_reason_codes"]
    for i in range(1, len(top)):
        prev = top[i - 1]
        cur = top[i]
        assert prev["count"] > cur["count"] or (
            prev["count"] == cur["count"] and prev["reason_code"] <= cur["reason_code"]
        )
