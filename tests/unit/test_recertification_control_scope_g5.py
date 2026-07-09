from datetime import UTC, datetime, timedelta

from tests.helpers.auth_org import bootstrap_org_user


def _create_control(client, headers, title="Control G5"):
    resp = client.post("/api/v1/controls", headers=headers, json={"title": title, "control_type": "process", "criticality": "medium"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_control_test(client, headers, control_id, name, next_due_at):
    resp = client.post(
        f"/api/v1/controls/{control_id}/tests",
        headers=headers,
        json={
            "name": name,
            "test_type": "internal_metadata_check",
            "check_key": "control_status_implemented",
            "cadence": "monthly",
            "next_due_at": next_due_at.isoformat(),
        },
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_policy(client, headers, scope_type, scope_config_json):
    resp = client.post(
        "/api/v1/recertification/policies",
        headers=headers,
        json={
            "name": "Control scope policy",
            "scope_type": scope_type,
            "scope_config_json": scope_config_json,
            "cadence": "quarterly",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_control_run_respects_scope_config_json_and_persists_policy_id(client):
    ctx = bootstrap_org_user(client, email_prefix="recertctrl")
    headers = ctx["org_headers"]

    in_scope_control = _create_control(client, headers, "In scope control")
    out_scope_control = _create_control(client, headers, "Out of scope control")

    due_soon = datetime.now(UTC) + timedelta(days=1)
    in_scope_test = _create_control_test(client, headers, in_scope_control, "In-scope test", due_soon)
    _create_control_test(client, headers, out_scope_control, "Out-of-scope test", due_soon)

    policy = _create_policy(client, headers, "control", {"control_id": in_scope_control})
    assert policy["scope_config_json"] == {"control_id": in_scope_control}

    # /controls/due should respect scope_config_json when a policy_id is passed.
    due_resp = client.get(
        "/api/v1/recertification/controls/due",
        headers=headers,
        params={"policy_id": policy["id"], "due_within_days": 7},
    )
    assert due_resp.status_code == 200
    due_items = due_resp.json()
    assert {item["test_id"] for item in due_items} == {in_scope_test}

    # Without a policy, both due items are visible (no scoping).
    due_resp_all = client.get(
        "/api/v1/recertification/controls/due",
        headers=headers,
        params={"due_within_days": 7},
    )
    assert due_resp_all.status_code == 200
    assert len(due_resp_all.json()) == 2

    # /controls/run must persist policy_id on the run and only touch in-scope items.
    run_resp = client.post(
        "/api/v1/recertification/controls/run",
        headers=headers,
        json={"policy_id": policy["id"], "dry_run": False, "notify_owner": False, "due_within_days": 7, "limit": 50},
    )
    assert run_resp.status_code == 200
    run_body = run_resp.json()
    assert run_body["policy_id"] == policy["id"]
    assert run_body["due_count"] == 1
    assert run_body["task_count"] == 1
