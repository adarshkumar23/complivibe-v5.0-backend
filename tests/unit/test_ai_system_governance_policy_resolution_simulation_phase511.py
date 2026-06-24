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


def _create_policy_set(client, headers: dict[str, str], *, name: str, ack_text: str = "CONFIRM_SEQUENCE_APPLY_DURING_FREEZE") -> dict:
    policy = client.post(
        "/api/v1/ai-governance/guardrails/policy-sets",
        headers=headers,
        json={"name": name},
    )
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
        json={"reason": "go live"},
    )
    assert activate.status_code == 200
    return p


def _assign_policy(client, headers: dict[str, str], payload: dict) -> dict:
    response = client.post("/api/v1/ai-governance/guardrails/policy-assignments", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_phase511_simulation_no_persist_and_no_side_effects(client):
    org = bootstrap_org_user(client, email_prefix="p511-no-persist")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P511 AI")
    pack = _create_pack(client, headers, name="P511 Pack")
    policy = _create_policy_set(client, headers, name="P511 Policy", ack_text="ACK_P511")
    _assign_policy(
        client,
        headers,
        {
            "policy_set_id": policy["id"],
            "scope_type": "ai_system",
            "scope_id": ai["id"],
            "reason": "ai default",
        },
    )

    now = datetime.now(UTC).replace(microsecond=0)
    freeze = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "P511 Freeze",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "freeze",
            "enforcement_level": "block",
            "override_allowed": True,
        },
    )
    assert freeze.status_code == 201

    response = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={
            "persist_report": False,
            "contexts": [
                {
                    "context_key": "blocked-ctx",
                    "sequence_pack_id": pack["id"],
                    "ai_system_ids": [ai["id"]],
                    "review_types": ["initial_review"],
                    "planned_start": now.isoformat(),
                    "planned_end": (now + timedelta(hours=1)).isoformat(),
                },
                {
                    "context_key": "no-policy-ctx",
                    "review_types": ["initial_review"],
                    "planned_start": (now + timedelta(days=10)).isoformat(),
                    "planned_end": (now + timedelta(days=10, hours=1)).isoformat(),
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is False
    assert body["report_id"] is None
    assert body["context_count"] == 2
    assert body["blocked_contexts_count"] == 1
    assert body["no_policy_contexts_count"] == 1
    assert "read-only planning reports" in body["caveat"]

    reports = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports", headers=headers)
    assert reports.status_code == 200
    assert reports.json() == []

    runs = client.get("/api/v1/ai-governance/review-sequence-runs", headers=headers)
    assert runs.status_code == 200
    assert runs.json() == []

    acknowledgements = client.get("/api/v1/ai-governance/guardrails/operator-acknowledgements", headers=headers)
    assert acknowledgements.status_code == 200
    assert acknowledgements.json() == []

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_resolution_simulation.generated" not in actions


def test_phase511_persisted_report_list_detail_archive_summary_and_audit(client):
    org = bootstrap_org_user(client, email_prefix="p511-persist")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P511 Persist AI")
    pack = _create_pack(client, headers, name="P511 Persist Pack")
    policy = _create_policy_set(client, headers, name="P511 Persist Policy")
    _assign_policy(
        client,
        headers,
        {
            "policy_set_id": policy["id"],
            "scope_type": "all_ai_governance",
            "reason": "global default",
        },
    )

    now = datetime.now(UTC).replace(microsecond=0)
    freeze_warn = client.post(
        "/api/v1/ai-governance/guardrails/freeze-windows",
        headers=headers,
        json={
            "name": "P511 Warn",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "scope_type": "all_ai_governance",
            "reason": "warn",
            "enforcement_level": "warn",
        },
    )
    assert freeze_warn.status_code == 201

    simulate = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={
            "title": "P511 Simulation",
            "description": "persist this",
            "persist_report": True,
            "contexts": [
                {
                    "context_key": "warn-ctx",
                    "sequence_pack_id": pack["id"],
                    "ai_system_ids": [ai["id"]],
                    "review_types": ["initial_review"],
                    "planned_start": now.isoformat(),
                    "planned_end": (now + timedelta(hours=1)).isoformat(),
                }
            ],
        },
    )
    assert simulate.status_code == 200
    body = simulate.json()
    assert body["persisted"] is True
    assert body["report_id"] is not None
    assert body["warning_contexts_count"] == 1

    report_id = body["report_id"]
    list_reports = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports", headers=headers)
    assert list_reports.status_code == 200
    assert any(item["id"] == report_id for item in list_reports.json())

    detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{report_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["id"] == report_id
    assert detail.json()["status"] == "generated"

    summary_before = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-summary", headers=headers)
    assert summary_before.status_code == 200
    assert summary_before.json()["total_reports"] >= 1

    archived = client.post(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{report_id}/archive",
        headers=headers,
        json={"reason": "done"},
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"

    summary_after = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-summary", headers=headers)
    assert summary_after.status_code == 200
    assert summary_after.json()["archived_reports"] >= 1

    logs = client.get("/api/v1/audit-logs", headers=headers)
    assert logs.status_code == 200
    actions = {item["action"] for item in logs.json()}
    assert "ai_system_governance_policy_resolution_simulation.generated" in actions
    assert "ai_system_governance_policy_resolution_simulation.archived" in actions


def test_phase511_simulation_tenant_scoping_and_report_tenant_visibility(client):
    org1 = bootstrap_org_user(client, email_prefix="p511-org1")
    org2 = bootstrap_org_user(client, email_prefix="p511-org2")
    h1 = org1["org_headers"]
    h2 = org2["org_headers"]

    ai1 = _create_ai_system(client, h1, name="P511 T1 AI")
    pack1 = _create_pack(client, h1, name="P511 T1 Pack")

    ai2 = _create_ai_system(client, h2, name="P511 T2 AI")
    pack2 = _create_pack(client, h2, name="P511 T2 Pack")

    invalid_pack = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=h1,
        json={
            "contexts": [{"sequence_pack_id": pack2["id"]}],
        },
    )
    assert invalid_pack.status_code == 404

    invalid_ai = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=h1,
        json={
            "contexts": [{"ai_system_ids": [ai2["id"]]}],
        },
    )
    assert invalid_ai.status_code == 404

    r1 = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=h1,
        json={"persist_report": True, "contexts": [{"sequence_pack_id": pack1["id"], "ai_system_ids": [ai1["id"]]}]},
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=h2,
        json={"persist_report": True, "contexts": [{"sequence_pack_id": pack2["id"], "ai_system_ids": [ai2["id"]]}]},
    )
    assert r2.status_code == 200

    list1 = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports", headers=h1)
    list2 = client.get("/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports", headers=h2)
    assert list1.status_code == 200 and list2.status_code == 200
    ids1 = {item["id"] for item in list1.json()}
    ids2 = {item["id"] for item in list2.json()}
    assert r1.json()["report_id"] in ids1
    assert r2.json()["report_id"] in ids2
    assert r2.json()["report_id"] not in ids1

    cross_detail = client.get(
        f"/api/v1/ai-governance/guardrails/policy-resolution/simulation-reports/{r2.json()['report_id']}",
        headers=h1,
    )
    assert cross_detail.status_code == 404


def test_phase511_simulation_explicit_vs_mapped_and_missing_active_version(client):
    org = bootstrap_org_user(client, email_prefix="p511-precedence")
    headers = org["org_headers"]

    ai = _create_ai_system(client, headers, name="P511 Precedence AI")
    pack = _create_pack(client, headers, name="P511 Precedence Pack")

    mapped_policy = _create_policy_set(client, headers, name="Mapped Policy", ack_text="ACK_MAPPED")
    explicit_policy = _create_policy_set(client, headers, name="Explicit Policy", ack_text="ACK_EXPLICIT")
    _assign_policy(
        client,
        headers,
        {
            "policy_set_id": mapped_policy["id"],
            "scope_type": "sequence_pack",
            "scope_id": pack["id"],
            "reason": "pack default",
        },
    )

    now = datetime.now(UTC).replace(microsecond=0)
    check = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={
            "contexts": [
                {
                    "context_key": "mapped",
                    "sequence_pack_id": pack["id"],
                    "ai_system_ids": [ai["id"]],
                    "review_types": ["initial_review"],
                    "planned_start": now.isoformat(),
                    "planned_end": (now + timedelta(hours=1)).isoformat(),
                },
                {
                    "context_key": "explicit",
                    "explicit_policy_set_id": explicit_policy["id"],
                    "sequence_pack_id": pack["id"],
                    "ai_system_ids": [ai["id"]],
                    "review_types": ["initial_review"],
                    "planned_start": now.isoformat(),
                    "planned_end": (now + timedelta(hours=1)).isoformat(),
                },
            ]
        },
    )
    assert check.status_code == 200
    contexts = {item["context_key"]: item for item in check.json()["contexts"]}
    assert contexts["mapped"]["policy_resolution"]["resolution_source"] == "mapped_sequence_pack"
    assert contexts["explicit"]["policy_resolution"]["resolution_source"] == "explicit_request"

    inactive_policy = client.post(
        "/api/v1/ai-governance/guardrails/policy-sets",
        headers=headers,
        json={"name": "No Active"},
    )
    assert inactive_policy.status_code == 201
    _assign_policy(
        client,
        headers,
        {
            "policy_set_id": inactive_policy.json()["id"],
            "scope_type": "ai_system",
            "scope_id": ai["id"],
            "reason": "bad mapping",
            "priority": 999,
        },
    )

    missing_active = client.post(
        "/api/v1/ai-governance/guardrails/policy-resolution/simulate",
        headers=headers,
        json={
            "contexts": [{"ai_system_ids": [ai["id"]], "review_types": ["initial_review"]}],
        },
    )
    assert missing_active.status_code == 400
