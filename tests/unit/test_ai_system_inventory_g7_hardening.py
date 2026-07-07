from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

SYSTEMS_BASE = "/api/v1/ai-governance/systems"


def _system_payload(owner_id: str, *, name: str, system_type: str = "model", deployment_status: str = "development") -> dict:
    return {
        "name": name,
        "system_type": system_type,
        "owner_id": owner_id,
        "deployment_status": deployment_status,
    }


def test_summary_is_empty_and_correct_for_org_with_no_systems(client):
    org = bootstrap_org_user(client, email_prefix="g7-inv-empty")
    summary = client.get(f"{SYSTEMS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body == {
        "total": 0,
        "by_system_type": {},
        "by_deployment_status": {},
        "by_risk_tier": {},
        "unclassified_count": 0,
    }


def test_summary_aggregates_correctly_via_sql_not_python_loop(client):
    org = bootstrap_org_user(client, email_prefix="g7-inv-agg")

    # 3 models (2 development, 1 staging), 2 agents (both development).
    specs = [
        ("model", "development"),
        ("model", "development"),
        ("model", "staging"),
        ("agent", "development"),
        ("agent", "development"),
    ]
    for idx, (system_type, deployment_status) in enumerate(specs):
        resp = client.post(
            SYSTEMS_BASE,
            headers=org["org_headers"],
            json=_system_payload(org["user_id"], name=f"agg-system-{idx}", system_type=system_type, deployment_status=deployment_status),
        )
        assert resp.status_code == 201

    summary = client.get(f"{SYSTEMS_BASE}/summary", headers=org["org_headers"])
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] == 5
    assert body["by_system_type"] == {"model": 3, "agent": 2}
    assert body["by_deployment_status"] == {"development": 4, "staging": 1}
    # None of these were classified yet -> all bucketed as unassessed.
    assert body["by_risk_tier"] == {"unassessed": 5}
    assert body["unclassified_count"] == 5


def test_duplicate_name_registration_does_not_crash_and_creates_distinct_systems(client):
    org = bootstrap_org_user(client, email_prefix="g7-inv-dup")

    first = client.post(SYSTEMS_BASE, headers=org["org_headers"], json=_system_payload(org["user_id"], name="Same Name"))
    second = client.post(SYSTEMS_BASE, headers=org["org_headers"], json=_system_payload(org["user_id"], name="Same Name"))
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]

    listed = client.get(SYSTEMS_BASE, headers=org["org_headers"])
    names = [row["name"] for row in listed.json()]
    assert names.count("Same Name") == 2


def test_unicode_and_max_length_name_round_trip(client):
    org = bootstrap_org_user(client, email_prefix="g7-inv-unicode")

    unicode_name = "AI 系统 - Système d'IA \U0001F916"
    resp = client.post(SYSTEMS_BASE, headers=org["org_headers"], json=_system_payload(org["user_id"], name=unicode_name))
    assert resp.status_code == 201
    assert resp.json()["name"] == unicode_name

    long_name = "A" * 255
    resp2 = client.post(SYSTEMS_BASE, headers=org["org_headers"], json=_system_payload(org["user_id"], name=long_name))
    assert resp2.status_code == 201
    assert len(resp2.json()["name"]) == 255

    too_long_name = "A" * 256
    resp3 = client.post(SYSTEMS_BASE, headers=org["org_headers"], json=_system_payload(org["user_id"], name=too_long_name))
    assert resp3.status_code == 422


def test_list_pagination_bounds_hold_at_scale(client):
    org = bootstrap_org_user(client, email_prefix="g7-inv-scale")
    for idx in range(12):
        resp = client.post(SYSTEMS_BASE, headers=org["org_headers"], json=_system_payload(org["user_id"], name=f"scale-{idx}"))
        assert resp.status_code == 201

    page = client.get(f"{SYSTEMS_BASE}?skip=0&limit=5", headers=org["org_headers"])
    assert page.status_code == 200
    assert len(page.json()) == 5

    too_big = client.get(f"{SYSTEMS_BASE}?limit=99999", headers=org["org_headers"])
    assert too_big.status_code == 422
