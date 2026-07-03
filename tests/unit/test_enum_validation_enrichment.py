from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _create_ai_system(client, headers):
    resp = client.post("/api/v1/ai-systems", headers=headers, json={"name": "FixD AI System", "system_type": "agent"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_verify_enum_error_enrichment_ai_governance(client):
    """AI Governance: EU AI Act classification article_category."""
    org = bootstrap_org_user(client, email_prefix="fixD-aig")
    system = _create_ai_system(client, org["org_headers"])

    resp = client.post(
        f"{SYSTEMS_BASE}/{system['id']}/eu-act-classification",
        headers=org["org_headers"],
        json={"article_category": "totally_not_a_real_category"},
    )
    print("AI GOVERNANCE ENUM ERROR:", resp.status_code, resp.json())
    assert resp.status_code == 422
    body = resp.json()
    assert "valid_options" in body
    assert len(body["valid_options"]) > 0
    assert body["field"] == "article_category"


def test_verify_enum_error_enrichment_data_observability(client):
    """Data Observability / Governance retention: retention policy entity_type."""
    org = bootstrap_org_user(client, email_prefix="fixD-do")
    resp = client.post(
        "/api/v1/governance/retention/policies",
        headers=org["org_headers"],
        json={"name": "Bad", "entity_type": "not_a_real_entity", "retention_days": 30, "lock_days": 7},
    )
    print("DATA OBSERVABILITY ENUM ERROR:", resp.status_code, resp.json())
    assert resp.status_code == 400
    body = resp.json()
    assert "valid_options" in body
    assert len(body["valid_options"]) > 0
    assert body["field"] == "entity_type"


def test_verify_enum_error_enrichment_controls(client):
    """Controls: control test definition test_type."""
    org = bootstrap_org_user(client, email_prefix="fixD-ctrl")
    control = client.post(
        "/api/v1/controls",
        headers=org["org_headers"],
        json={"title": "FixD Control", "description": "d", "control_type": "process", "criticality": "medium"},
    )
    control_id = control.json()["id"]

    resp = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=org["org_headers"],
        json={
            "name": "Bad test",
            "test_type": "not_a_real_type",
            "check_key": "manual_attestation",
            "cadence": "monthly",
            "owner_user_id": org["user_id"],
        },
    )
    print("CONTROLS ENUM ERROR:", resp.status_code, resp.json())
    assert resp.status_code == 422
    body = resp.json()
    err = body["detail"][0]
    assert "valid_options" in err
    assert set(err["valid_options"]) == {"manual_attestation", "internal_metadata_check", "evidence_review_check"}


def test_verify_enum_error_enrichment_governance_automation(client):
    """Governance Automation: automation rule condition_type."""
    org = bootstrap_org_user(client, email_prefix="fixD-gov")
    resp = client.post(
        "/api/v1/automation/rules",
        headers=org["org_headers"],
        json={
            "name": "Bad rule",
            "trigger_type": "manual_scan",
            "condition_type": "not_a_real_condition",
            "condition_config_json": {},
            "action_type": "create_task",
            "action_config_json": {},
        },
    )
    print("GOVERNANCE AUTOMATION ENUM ERROR:", resp.status_code, resp.json())
    assert resp.status_code == 400
    body = resp.json()
    assert "valid_options" in body
    assert len(body["valid_options"]) > 0
    assert body["field"] == "condition_type"
