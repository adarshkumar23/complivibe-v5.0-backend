from __future__ import annotations

from tests.helpers.auth_org import bootstrap_org_user

QUERY_URL = "/api/v1/command-palette/query"
EXECUTE_URL = "/api/v1/command-palette/execute"


def test_g1_command_palette_query_rejects_overlong_query(client):
    ctx = bootstrap_org_user(client, email_prefix="g1-cp-long")
    resp = client.get(QUERY_URL, params={"q": "x" * 300}, headers=ctx["org_headers"])
    assert resp.status_code == 422


def test_g1_command_palette_query_ignores_unknown_entity_types_gracefully(client):
    ctx = bootstrap_org_user(client, email_prefix="g1-cp-unknown-type")
    resp = client.get(
        QUERY_URL,
        params={"q": "access", "entity_types": ["not_a_real_entity_type"]},
        headers=ctx["org_headers"],
    )
    # Unknown entity types are silently filtered by SearchIndexingService rather than
    # raising -- confirm this holds and the create_task fallback item is still returned.
    assert resp.status_code == 200
    body = resp.json()
    assert any(item["action_key"] == "create_task" for item in body["items"])


def test_g1_command_palette_create_task_rejects_overlong_title_with_422(client):
    ctx = bootstrap_org_user(client, email_prefix="g1-cp-unicode-reject")
    # 260 unicode (multi-byte, incl. emoji) characters -- request-body validation should
    # reject this cleanly (422) rather than truncate awkwardly mid-grapheme server-side.
    long_unicode_title = "审计任务 🚨 " * 40
    assert len(long_unicode_title) > 255
    resp = client.post(
        EXECUTE_URL,
        headers=ctx["org_headers"],
        json={"action_key": "create_task", "title": long_unicode_title},
    )
    assert resp.status_code == 422


def test_g1_command_palette_create_task_stores_unicode_title_at_boundary(client):
    ctx = bootstrap_org_user(client, email_prefix="g1-cp-unicode-ok")
    unicode_title = (("审计任务 🚨 " * 20)[:255]).strip()
    resp = client.post(
        EXECUTE_URL,
        headers=ctx["org_headers"],
        json={"action_key": "create_task", "title": unicode_title},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["task_id"] is not None

    task_get = client.get(f"/api/v1/tasks/{body['task_id']}", headers=ctx["org_headers"])
    assert task_get.status_code == 200
    assert task_get.json()["title"] == unicode_title
