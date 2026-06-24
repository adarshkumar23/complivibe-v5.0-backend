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


def _persist_sim(client, headers: dict[str, str], contexts: list[dict], *, title: str = "sim") -> str:
    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={"persist_report": True, "title": title, "contexts": contexts},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["report_id"] is not None
    return body["report_id"]


def test_phase512_diff_without_persistence_no_write_and_no_audit(client):
    org = bootstrap_org_user(client, email_prefix="p512-no-persist")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P512 AI")
    pack = _create_pack(client, headers, name="P512 Pack")
    policy = _create_policy_set(client, headers, name="P512 Policy", ack_text="ACK1")
    _assign(
        client,
        headers,
        {"policy_set_id": policy["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "pack"},
    )

    now = datetime.now(UTC).replace(microsecond=0)
    r1 = _persist_sim(
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

    freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "block",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "freeze",
            "enforcement_level": "block",
            "override_allowed": True,
        },
    )
    assert freeze.status_code == 201

    r2 = _persist_sim(
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
        title="compare",
    )

    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={"base_report_id": r1, "compare_report_id": r2, "persist_diff": False},
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["persisted"] is False
    assert body["diff_report_id"] is None
    assert body["changed_contexts_count"] == 1
    assert body["blocked_delta"] == 1

    reports = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports", headers=headers)
    assert reports.status_code == 200
    assert reports.json() == []

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_resolution_simulation_diff.generated" not in actions


def test_phase512_diff_persist_list_detail_archive_summary_and_audit(client):
    org = bootstrap_org_user(client, email_prefix="p512-persist")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P512 Persist AI")
    pack = _create_pack(client, headers, name="P512 Persist Pack")

    policy_mapped = _create_policy_set(client, headers, name="Mapped", ack_text="ACK_M")
    policy_explicit = _create_policy_set(client, headers, name="Explicit", ack_text="ACK_E")
    _assign(
        client,
        headers,
        {"policy_set_id": policy_mapped["id"], "scope_type": "sequence_pack", "scope_id": pack["id"], "reason": "pack"},
    )

    now = datetime.now(UTC).replace(microsecond=0)
    base = _persist_sim(
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
    compare = _persist_sim(
        client,
        headers,
        [
            {
                "context_key": "ctx-1",
                "explicit_policy_set_id": policy_explicit["id"],
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["initial_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=1)).isoformat(),
            },
            {
                "context_key": "ctx-2",
                "sequence_pack_id": pack["id"],
                "ai_system_ids": [ai["id"]],
                "review_types": ["periodic_review"],
                "planned_start": now.isoformat(),
                "planned_end": (now + timedelta(hours=2)).isoformat(),
            },
        ],
        title="compare",
    )

    diff = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=headers,
        json={
            "base_report_id": base,
            "compare_report_id": compare,
            "persist_diff": True,
            "title": "delta",
            "context_match_strategy": "context_key_then_index",
        },
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["persisted"] is True
    assert body["diff_report_id"] is not None
    assert body["added_contexts_count"] == 1
    assert body["removed_contexts_count"] == 0
    assert body["policy_changed_count"] >= 1

    diff_id = body["diff_report_id"]
    list_reports = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports", headers=headers)
    assert list_reports.status_code == 200
    assert any(item["id"] == diff_id for item in list_reports.json())

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == diff_id

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-reports/{diff_id}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-diff-summary", headers=headers)
    assert summary.status_code == 200
    s = summary.json()
    assert s["total_diff_reports"] >= 1
    assert s["archived_diff_reports"] >= 1
    assert s["total_added_contexts"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_resolution_simulation_diff.generated" in actions
    assert "ai_system_governance_policy_resolution_simulation_diff.archived" in actions


def test_phase512_diff_tenant_isolation_and_index_fallback(client):
    org1 = bootstrap_org_user(client, email_prefix="p512-t1")
    org2 = bootstrap_org_user(client, email_prefix="p512-t2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    ai1 = _create_ai_system(client, h1, name="P512 T1 AI")
    pack1 = _create_pack(client, h1, name="P512 T1 Pack")
    ai2 = _create_ai_system(client, h2, name="P512 T2 AI")
    pack2 = _create_pack(client, h2, name="P512 T2 Pack")

    r1 = _persist_sim(client, h1, [{"sequence_pack_id": pack1["id"], "ai_system_ids": [ai1["id"]]}], title="r1")
    r2 = _persist_sim(client, h1, [{"sequence_pack_id": pack1["id"], "ai_system_ids": [ai1["id"]]}], title="r2")
    r_other = _persist_sim(client, h2, [{"sequence_pack_id": pack2["id"], "ai_system_ids": [ai2["id"]]}], title="r3")

    bad_base = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=h1,
        json={"base_report_id": r_other, "compare_report_id": r2},
    )
    assert bad_base.status_code == 404

    bad_compare = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=h1,
        json={"base_report_id": r1, "compare_report_id": r_other},
    )
    assert bad_compare.status_code == 404

    by_index = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=h1,
        json={
            "base_report_id": r1,
            "compare_report_id": r2,
            "context_match_strategy": "context_key_then_index",
        },
    )
    assert by_index.status_code == 200
    assert by_index.json()["added_contexts_count"] == 0
    assert by_index.json()["removed_contexts_count"] == 0

    key_only = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/diff",
        headers=h1,
        json={
            "base_report_id": r1,
            "compare_report_id": r2,
            "context_match_strategy": "context_key_only",
        },
    )
    assert key_only.status_code == 200
    assert key_only.json()["added_contexts_count"] == 1
    assert key_only.json()["removed_contexts_count"] == 1
