from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.bcm import BusinessProcess
from app.models.risk import Risk
from tests.helpers.auth_org import bootstrap_org_user


def _create_playbook(client, headers, **overrides):
    payload = {
        "name": "Cyber Incident Response Playbook",
        "scenario_type": "cyber_incident",
        "steps_json": [
            {"step": "Contain the incident"},
            {"step": "Notify stakeholders"},
        ],
        "owner_team": "Security",
    }
    payload.update(overrides)
    return client.post("/api/v1/crisis/playbooks", headers=headers, json=payload)


def test_crisis_management_permissions_seeded(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-perms")

    rows = db_session.execute(
        sa.text(
            "SELECT key FROM permissions WHERE key IN ('crisis_management:read', 'crisis_management:manage')"
        )
    ).scalars().all()
    assert set(rows) == {"crisis_management:read", "crisis_management:manage"}

    response = client.get("/api/v1/auth/permissions", headers=org_user["org_headers"])
    assert response.status_code == 200, response.text
    codes = response.json()["permission_codes"]
    assert "crisis_management:read" in codes
    assert "crisis_management:manage" in codes


def test_create_and_activate_playbook_happy_path(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-happy")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers)
    assert resp.status_code == 201, resp.text
    playbook = resp.json()
    assert playbook["scenario_type"] == "cyber_incident"
    assert playbook["status"] == "active"

    activate_resp = client.post(f"/api/v1/crisis/playbooks/{playbook['id']}/activate", headers=headers)
    assert activate_resp.status_code == 201, activate_resp.text
    activation = activate_resp.json()
    assert activation["status"] == "active"
    assert activation["playbook_id"] == playbook["id"]
    assert activation["linked_processes_json"] == []
    assert activation["linked_risks_json"] == []

    active_resp = client.get("/api/v1/crisis/active", headers=headers)
    assert active_resp.status_code == 200, active_resp.text
    active_ids = [item["id"] for item in active_resp.json()]
    assert activation["id"] in active_ids


def test_activation_links_critical_business_process(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-proc")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    process = BusinessProcess(
        organization_id=organization_id,
        name="Core Payments Processing",
        criticality_tier="tier_1_critical",
        recovery_time_objective_hours=2,
        recovery_point_objective_hours=1,
        status="active",
    )
    db_session.add(process)
    db_session.commit()
    process_id = str(process.id)

    resp = _create_playbook(client, headers, scenario_type="natural_disaster")
    assert resp.status_code == 201, resp.text
    playbook_id = resp.json()["id"]

    activate_resp = client.post(f"/api/v1/crisis/playbooks/{playbook_id}/activate", headers=headers)
    assert activate_resp.status_code == 201, activate_resp.text
    linked_processes = activate_resp.json()["linked_processes_json"]
    assert any(item["process_id"] == process_id for item in linked_processes)
    matched = next(item for item in linked_processes if item["process_id"] == process_id)
    assert matched["criticality_tier"] == "tier_1_critical"
    assert matched["name"] == "Core Payments Processing"


def test_activation_links_high_severity_and_keyword_matched_risks(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-risk")
    headers = org_user["org_headers"]
    organization_id = uuid.UUID(org_user["organization_id"])

    cyber_risk = Risk(
        organization_id=organization_id,
        title="Cybersecurity vulnerability in payment gateway",
        category="cyber",
        severity="medium",
        status="identified",
    )
    unrelated_high_risk = Risk(
        organization_id=organization_id,
        title="Unrelated supplier delay",
        category="operational",
        severity="critical",
        status="identified",
    )
    irrelevant_low_risk = Risk(
        organization_id=organization_id,
        title="Minor office facilities issue",
        category="facilities",
        severity="low",
        status="identified",
    )
    db_session.add_all([cyber_risk, unrelated_high_risk, irrelevant_low_risk])
    db_session.commit()
    cyber_risk_id = str(cyber_risk.id)
    unrelated_high_risk_id = str(unrelated_high_risk.id)
    irrelevant_low_risk_id = str(irrelevant_low_risk.id)

    resp = _create_playbook(client, headers, scenario_type="cyber_incident")
    assert resp.status_code == 201, resp.text
    playbook_id = resp.json()["id"]

    activate_resp = client.post(f"/api/v1/crisis/playbooks/{playbook_id}/activate", headers=headers)
    assert activate_resp.status_code == 201, activate_resp.text
    linked_risk_ids = {item["risk_id"] for item in activate_resp.json()["linked_risks_json"]}

    assert cyber_risk_id in linked_risk_ids
    assert unrelated_high_risk_id in linked_risk_ids
    assert irrelevant_low_risk_id not in linked_risk_ids


def test_resolve_activation_happy_path(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-resolve")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers)
    assert resp.status_code == 201, resp.text
    playbook_id = resp.json()["id"]

    activate_resp = client.post(f"/api/v1/crisis/playbooks/{playbook_id}/activate", headers=headers)
    assert activate_resp.status_code == 201, activate_resp.text
    activation_id = activate_resp.json()["id"]

    resolve_resp = client.post(
        f"/api/v1/crisis/activations/{activation_id}/resolve",
        headers=headers,
        json={"resolution_notes": "Incident contained and resolved."},
    )
    assert resolve_resp.status_code == 200, resolve_resp.text
    resolved = resolve_resp.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolution_notes"] == "Incident contained and resolved."
    assert resolved["resolved_at"] is not None

    active_resp = client.get("/api/v1/crisis/active", headers=headers)
    assert active_resp.status_code == 200, active_resp.text
    active_ids = [item["id"] for item in active_resp.json()]
    assert activation_id not in active_ids


def test_resolving_already_resolved_activation_returns_400(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-doubleresolve")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers)
    assert resp.status_code == 201, resp.text
    playbook_id = resp.json()["id"]

    activate_resp = client.post(f"/api/v1/crisis/playbooks/{playbook_id}/activate", headers=headers)
    assert activate_resp.status_code == 201, activate_resp.text
    activation_id = activate_resp.json()["id"]

    first_resolve = client.post(
        f"/api/v1/crisis/activations/{activation_id}/resolve", headers=headers, json={}
    )
    assert first_resolve.status_code == 200, first_resolve.text

    second_resolve = client.post(
        f"/api/v1/crisis/activations/{activation_id}/resolve", headers=headers, json={}
    )
    assert second_resolve.status_code == 400, second_resolve.text


def test_activating_archived_or_draft_playbook_returns_4xx(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-archived")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers, status="draft")
    assert resp.status_code == 201, resp.text
    playbook_id = resp.json()["id"]

    activate_resp = client.post(f"/api/v1/crisis/playbooks/{playbook_id}/activate", headers=headers)
    assert activate_resp.status_code == 400, activate_resp.text

    resp2 = _create_playbook(client, headers, status="archived", name="Archived Playbook")
    assert resp2.status_code == 201, resp2.text
    archived_playbook_id = resp2.json()["id"]

    activate_resp2 = client.post(f"/api/v1/crisis/playbooks/{archived_playbook_id}/activate", headers=headers)
    assert activate_resp2.status_code == 400, activate_resp2.text


def test_empty_steps_json_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-badsteps")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers, steps_json=[])
    assert resp.status_code == 422, resp.text


def test_malformed_steps_json_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-malformedsteps")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers, steps_json=[{"foo": "bar"}])
    assert resp.status_code == 422, resp.text


def test_invalid_scenario_type_returns_422(client, db_session):
    org_user = bootstrap_org_user(client, email_prefix="crisis-badscenario")
    headers = org_user["org_headers"]

    resp = _create_playbook(client, headers, scenario_type="not_a_real_scenario")
    assert resp.status_code == 422, resp.text
