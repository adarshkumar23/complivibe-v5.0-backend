from tests.helpers.auth_org import bootstrap_org_user


def test_phase79_phase7_contract_reports_execution_safety_boundary(client):
    org = bootstrap_org_user(client, email_prefix="p79-contract")
    resp = client.get("/api/v1/ai-governance/contracts/phase7", headers=org["org_headers"])
    assert resp.status_code == 200
    body = resp.json()

    assert body["phase"] == "phase7"
    assert body["execution_allowed"] is False
    assert body["real_runner_present"] is False
    assert body["job_queue_present"] is False
    assert body["future_runner_requires_architecture_review"] is True

    caveat = body["caveat"].lower()
    assert "no real runner exists" in caveat
    assert "does not execute automation" in caveat
    assert "does not make legal or regulatory determinations" in caveat

    groups = {group["group_key"] for group in body["groups"]}
    assert "governance_autopilot_runner_interface" in groups
    assert "governance_autopilot_runner_simulations" in groups
    assert "governance_autopilot_runner_admissions" in groups
    assert "governance_autopilot_runner_sessions" in groups
    assert "governance_autopilot_runner_handshakes" in groups
