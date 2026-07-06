from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.risk import Risk
from app.models.task import Task
from app.services.search_indexing_service import SearchIndexingService
from tests.helpers.auth_org import bootstrap_org_user


def test_ux1_command_palette_query_and_execute_create_task(client, db_session, monkeypatch):
    ctx = bootstrap_org_user(client, email_prefix="ux1-cmd")
    org_id = uuid.UUID(ctx["organization_id"])
    user_id = uuid.UUID(ctx["user_id"])

    def _fake_search(self, *, query, organization_id, entity_types=None, limit=20):  # noqa: ANN001
        return {
            "query": query,
            "took_ms": 4,
            "hits": [
                {
                    "entity_type": "risk",
                    "id": str(uuid.uuid4()),
                    "organization_id": str(organization_id),
                    "title": "Vendor data residency gap",
                    "severity": "high",
                    "_rankingScore": 0.82,
                }
            ],
        }

    monkeypatch.setattr(SearchIndexingService, "search", _fake_search)

    query_resp = client.get(
        "/api/v1/command-palette/query",
        params={"q": "vendor data"},
        headers=ctx["org_headers"],
    )
    assert query_resp.status_code == 200, query_resp.text
    payload = query_resp.json()
    assert payload["query"] == "vendor data"
    assert len(payload["items"]) >= 2
    assert any(item["item_type"] == "entity" and item["action_key"] == "navigate_entity" for item in payload["items"])
    assert any(item["item_type"] == "action" and item["action_key"] == "create_task" for item in payload["items"])

    exec_resp = client.post(
        "/api/v1/command-palette/execute",
        headers=ctx["org_headers"],
        json={"action_key": "create_task", "title": "Investigate vendor data gap"},
    )
    assert exec_resp.status_code == 200, exec_resp.text
    result = exec_resp.json()
    assert result["action_key"] == "create_task"
    task_id = uuid.UUID(result["task_id"])

    row = db_session.get(Task, task_id)
    assert row is not None
    assert row.organization_id == org_id
    assert row.owner_user_id == user_id
    assert row.title == "Investigate vendor data gap"

    audit_row = db_session.execute(
        select(AuditLog).where(
            AuditLog.organization_id == org_id,
            AuditLog.entity_type == "task",
            AuditLog.entity_id == task_id,
            AuditLog.action == "command_palette.task_created",
        )
    ).scalar_one_or_none()
    assert audit_row is not None


def test_ux1_command_palette_execute_rejects_cross_tenant_linked_entity(client, db_session):
    org_a = bootstrap_org_user(client, email_prefix="ux1-org-a")
    org_b = bootstrap_org_user(client, email_prefix="ux1-org-b")

    risk_b = Risk(
        organization_id=uuid.UUID(org_b["organization_id"]),
        title="Cross-tenant risk",
        created_by_user_id=uuid.UUID(org_b["user_id"]),
        severity="high",
        status="open",
    )
    db_session.add(risk_b)
    db_session.commit()

    resp = client.post(
        "/api/v1/command-palette/execute",
        headers=org_a["org_headers"],
        json={
            "action_key": "create_task",
            "title": "Try linking external risk",
            "entity_type": "risk",
            "entity_id": str(risk_b.id),
        },
    )
    assert resp.status_code == 404
