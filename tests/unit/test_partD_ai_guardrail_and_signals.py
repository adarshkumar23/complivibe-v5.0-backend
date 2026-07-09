from tests.helpers.auth_org import bootstrap_org_user


def test_verify_data_scope_guardrail_enforces(client):
    org = bootstrap_org_user(client, email_prefix="partD-guardrail")
    system = client.post("/api/v1/ai-systems", headers=org["org_headers"], json={"name": "GR System", "system_type": "agent"})
    system_id = system.json()["id"]

    guardrail = client.post(
        "/api/v1/ai-governance/guardrails",
        headers=org["org_headers"],
        json={
            "ai_system_id": system_id,
            "guardrail_type": "data_scope",
            "constraint_description": "Only allow public/internal data categories",
            "constraint_value": {"allowed_data_categories": ["public", "internal"]},
            "violation_action": "block_and_alert",
        },
    )
    print("GUARDRAIL CREATE:", guardrail.status_code, guardrail.json())
    assert guardrail.status_code == 201, guardrail.text

    # Action requesting an out-of-scope data category should now be BLOCKED (was silently permitted before)
    blocked = client.post(
        f"/api/v1/ai-governance/systems/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={"action_context": {"data_categories": ["pii", "financial"]}},
    )
    print("BLOCKED CHECK:", blocked.status_code, blocked.json())
    assert blocked.status_code == 200
    assert blocked.json()["decision"] == "block", "BUG: data_scope guardrail is a silent no-op"

    # Action requesting only in-scope categories should be permitted
    allowed = client.post(
        f"/api/v1/ai-governance/systems/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={"action_context": {"data_categories": ["public"]}},
    )
    print("ALLOWED CHECK:", allowed.status_code, allowed.json())
    assert allowed.json()["decision"] == "permit"


def test_guardrail_create_rejects_unenforceable_constraint_value(client):
    org = bootstrap_org_user(client, email_prefix="partD-gr-constraint")
    system = client.post("/api/v1/ai-systems", headers=org["org_headers"], json={"name": "GR Constraint System", "system_type": "agent"})
    system_id = system.json()["id"]

    # Wrong key: the built-in engine reads max_usd, so max_amount would be a silent no-op.
    wrong_key = client.post(
        "/api/v1/ai-governance/guardrails",
        headers=org["org_headers"],
        json={
            "ai_system_id": system_id,
            "guardrail_type": "financial_limit",
            "constraint_description": "Max 1000",
            "constraint_value": {"max_amount": 1000},
            "violation_action": "block_and_alert",
        },
    )
    assert wrong_key.status_code == 422
    assert "max_usd" in wrong_key.json()["detail"]

    # Wrong value shape: list expected.
    wrong_shape = client.post(
        "/api/v1/ai-governance/guardrails",
        headers=org["org_headers"],
        json={
            "guardrail_type": "data_scope",
            "constraint_description": "Categories",
            "constraint_value": {"allowed_data_categories": "pii"},
        },
    )
    assert wrong_shape.status_code == 422

    # Correct key accepted and actually enforced.
    ok = client.post(
        "/api/v1/ai-governance/guardrails",
        headers=org["org_headers"],
        json={
            "ai_system_id": system_id,
            "guardrail_type": "financial_limit",
            "constraint_description": "Max 1000 USD",
            "constraint_value": {"max_usd": 1000},
            "violation_action": "block_and_alert",
        },
    )
    assert ok.status_code == 201

    blocked = client.post(
        f"/api/v1/ai-governance/systems/{system_id}/guardrails/check",
        headers=org["org_headers"],
        json={"action_context": {"estimated_value": 5000}},
    )
    assert blocked.status_code == 200
    assert blocked.json()["decision"] == "block"

    # approval_required needs no constraint keys.
    approval = client.post(
        "/api/v1/ai-governance/guardrails",
        headers=org["org_headers"],
        json={
            "guardrail_type": "approval_required",
            "constraint_description": "Needs approval",
            "constraint_value": {},
        },
    )
    assert approval.status_code == 201


def test_verify_output_drift_breach_auto_creates_risk_signal(client):
    org = bootstrap_org_user(client, email_prefix="partD-drift")
    system = client.post("/api/v1/ai-systems", headers=org["org_headers"], json={"name": "Drift System", "system_type": "agent"})
    system_id = system.json()["id"]

    config = client.post(
        f"/api/v1/ai-governance/systems/{system_id}/monitoring-configs",
        headers=org["org_headers"],
        json={
            "metric_type": "output_drift",
            "threshold_value": "0.20",
            "comparison_direction": "above",
            "api_key": "test-api-key-for-drift-config",
        },
    )
    print("CONFIG CREATE:", config.status_code, config.json())
    assert config.status_code == 201, config.text
    config_id = config.json()["id"]

    reading = client.post(
        "/api/v1/ai-governance/monitoring/readings",
        headers=org["org_headers"],
        json={"config_id": config_id, "value": "0.75"},
    )
    print("READING (breach):", reading.status_code, reading.json())
    assert reading.status_code == 201, reading.text

    signals = client.get("/api/v1/ai-governance/risk-signals", headers=org["org_headers"])
    print("SIGNALS:", signals.status_code, signals.json())
    assert signals.status_code == 200
    drift_signals = [s for s in signals.json() if s["signal_type"] == "output_distribution_shift"]
    assert drift_signals, "BUG: output_drift breach never auto-created a risk signal"
