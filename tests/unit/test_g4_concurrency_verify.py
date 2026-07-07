from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool


def _make_app(tmp_path):
    from app.main import create_application
    from app.core.deps import get_db
    from app.db.base import Base
    import app.models  # noqa: F401

    db_path = tmp_path / "concur.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=0,
        connect_args={"check_same_thread": False, "timeout": 60.0},
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)

    app = create_application()

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return app, engine, db_path


def _bootstrap_org_user(client):
    idx = uuid.uuid4().hex[:8]
    email = f"concur-{idx}@example.com"
    org_name = f"concur-org-{idx}"
    r = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Pass1234!@", "organization_name": org_name},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    orgs = client.get("/api/v1/organizations/me", headers={"Authorization": f"Bearer {token}"})
    assert orgs.status_code == 200, orgs.text
    org_id = orgs.json()[0]["id"]
    return token, org_id


def _headers(token, org_id):
    return {"Authorization": f"Bearer {token}", "X-Organization-ID": org_id}


def _fire_concurrent(app, specs, *, timeout: float = 30.0):
    """Fire a list of HTTP specs in near-parallel using per-thread TestClients.

    All workers rendezvous on a barrier so their requests leave at the same
    time -- this is the closest we can get to genuinely simultaneous calls
    with TestClient.
    """
    results: list = [None] * len(specs)
    barrier = threading.Barrier(len(specs), timeout=5.0)

    def worker(i, spec):
        try:
            with TestClient(app) as c:
                barrier.wait(timeout=5.0)
                method = spec.get("method", "POST")
                r = c.request(
                    method,
                    spec["url"],
                    headers=spec.get("headers"),
                    json=spec.get("json"),
                )
                body = r.json() if "application/json" in (r.headers.get("content-type") or "") else r.text
                results[i] = {"status": r.status_code, "body": body}
        except Exception as exc:  # pragma: no cover
            results[i] = {"status": None, "error": str(exc)}

    threads = [threading.Thread(target=worker, args=(i, s)) for i, s in enumerate(specs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
    return results


def test_concurrent_task_complete_race_returns_single_success(client, tmp_path):
    app, engine, _ = _make_app(tmp_path)
    with TestClient(app) as bootstrap_client:
        token, org_id = _bootstrap_org_user(bootstrap_client)
        headers = _headers(token, org_id)
        created = bootstrap_client.post("/api/v1/tasks", headers=headers, json={"title": "Race complete me"})
        assert created.status_code == 201
        task_id = created.json()["id"]

    specs = [{
        "url": f"/api/v1/tasks/{task_id}/complete",
        "headers": headers,
        "json": {"completion_notes": "done"},
    } for _ in range(2)]

    results = _fire_concurrent(app, specs)
    statuses = [r["status"] for r in results]

    assert sorted(statuses) == [200, 409], f"expected one success and one 409, got {results}"

    # The legitimate single-request path must still succeed normally afterwards.
    with TestClient(app) as c2:
        normal = c2.post("/api/v1/tasks", headers=headers, json={"title": "Normal complete"})
        assert normal.status_code == 201
        complete = c2.post(
            f"/api/v1/tasks/{normal.json()['id']}/complete",
            headers=headers,
            json={},
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"


def test_concurrent_task_cancel_race_returns_single_success(client, tmp_path):
    app, engine, _ = _make_app(tmp_path)
    with TestClient(app) as bootstrap_client:
        token, org_id = _bootstrap_org_user(bootstrap_client)
        headers = _headers(token, org_id)
        created = bootstrap_client.post("/api/v1/tasks", headers=headers, json={"title": "Race cancel me"})
        assert created.status_code == 201
        task_id = created.json()["id"]

    specs = [{
        "url": f"/api/v1/tasks/{task_id}/cancel",
        "headers": headers,
        "json": {"cancellation_reason": "no longer needed"},
    } for _ in range(2)]

    results = _fire_concurrent(app, specs)
    statuses = [r["status"] for r in results]
    assert sorted(statuses) == [200, 409], f"expected one success and one 409, got {results}"


def test_concurrent_issue_transition_race_is_blocked(client, tmp_path):
    app, engine, _ = _make_app(tmp_path)
    ISSUES_BASE = "/api/v1/compliance/issues"
    with TestClient(app) as bootstrap_client:
        token, org_id = _bootstrap_org_user(bootstrap_client)
        headers = _headers(token, org_id)
        issue = bootstrap_client.post(
            ISSUES_BASE,
            headers=headers,
            json={
                "title": "Race transition",
                "description": "desc",
                "issue_type": "custom",
                "severity": "medium",
                "source_type": "manual",
                "owner_id": _org_user_id_from_token(bootstrap_client, token),
            },
        )
        assert issue.status_code == 201
        issue_id = issue.json()["id"]

    specs = [{
        "url": f"{ISSUES_BASE}/{issue_id}/transition",
        "headers": headers,
        "json": {"new_status": "investigating"},
    } for _ in range(2)]

    results = _fire_concurrent(app, specs)
    statuses = [r["status"] for r in results]
    assert sorted(statuses) == [200, 422], f"expected one success and one 422, got {results}"

    with TestClient(app) as c2:
        history = c2.get(f"{ISSUES_BASE}/{issue_id}/transitions", headers=headers)
        assert history.status_code == 200
        to_statuses = [item["to_status"] for item in history.json()]
        assert to_statuses.count("investigating") == 1


def _create_issue_for_concurrency(client, headers):
    me = client.get("/api/v1/auth/me", headers={"Authorization": headers["Authorization"]})
    assert me.status_code == 200
    owner_id = me.json()["id"]
    r = client.post(
        "/api/v1/compliance/issues",
        headers=headers,
        json={
            "title": "RCA race issue",
            "description": "desc",
            "issue_type": "custom",
            "severity": "medium",
            "source_type": "manual",
            "owner_id": owner_id,
        },
    )
    assert r.status_code == 201
    return r.json()["id"], owner_id


def _org_user_id_from_token(client, token):
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    return me.json()["id"]


def test_concurrent_rca_creation_race_returns_single_success(client, tmp_path):
    app, engine, _ = _make_app(tmp_path)
    ISSUES_BASE = "/api/v1/compliance/issues"
    rca_payload = {
        "summary": "RCA",
        "timeline_description": "Timeline",
        "root_cause": "Cause",
        "contributing_factors": [],
        "corrective_actions": [],
        "preventive_measures": [],
    }

    with TestClient(app) as bootstrap_client:
        token, org_id = _bootstrap_org_user(bootstrap_client)
        headers = _headers(token, org_id)
        issue_id, _ = _create_issue_for_concurrency(bootstrap_client, headers)
        for state in ["investigating", "mitigating", "resolved"]:
            r = bootstrap_client.post(
                f"{ISSUES_BASE}/{issue_id}/transition",
                headers=headers,
                json={"new_status": state},
            )
            assert r.status_code == 200

    specs = [{
        "url": f"{ISSUES_BASE}/{issue_id}/rca",
        "headers": headers,
        "json": rca_payload,
    } for _ in range(2)]

    results = _fire_concurrent(app, specs)
    statuses = [r["status"] for r in results]
    assert sorted(statuses) == [201, 409], f"expected one RCA 201 and one 409, got {results}"


def test_concurrent_escalation_evaluate_double_fire_is_blocked(client, tmp_path):
    from datetime import UTC, datetime, timedelta

    app, engine, _ = _make_app(tmp_path)
    ISSUES_BASE = "/api/v1/compliance/issues"
    ESCALATIONS_BASE = "/api/v1/compliance/escalation-policies"

    with TestClient(app) as bootstrap_client:
        token, org_id = _bootstrap_org_user(bootstrap_client)
        headers = _headers(token, org_id)
        issue = bootstrap_client.post(
            ISSUES_BASE,
            headers=headers,
            json={
                "title": "Stuck issue",
                "description": "desc",
                "issue_type": "custom",
                "severity": "critical",
                "source_type": "manual",
                "owner_id": _org_user_id_from_token(bootstrap_client, token),
            },
        )
        assert issue.status_code == 201
        issue_id = issue.json()["id"]

        # Backdate updated_at so the time-in-state policy fires immediately.
        from sqlalchemy import update
        from app.models.issue import Issue as IssueModel
        with engine.begin() as conn:
            conn.execute(
                update(IssueModel)
                .where(IssueModel.id == uuid.UUID(issue_id))
                .values(updated_at=datetime.now(UTC) - timedelta(hours=5))
            )

        policy = bootstrap_client.post(
            ESCALATIONS_BASE,
            headers=headers,
            json={
                "name": "Stuck >2h",
                "entity_type": "issue",
                "condition_type": "time_in_state",
                "condition_value": {"hours": 2},
                "escalate_to_user_id": _org_user_id_from_token(bootstrap_client, token),
                "notification_message_template": "Escalation {entity_type} {entity_id} by {condition_type}",
            },
        )
        assert policy.status_code == 201

    specs = [{
        "url": f"{ESCALATIONS_BASE}/evaluate",
        "headers": headers,
        "json": None,
    } for _ in range(2)]

    results = _fire_concurrent(app, specs)
    statuses = [r["status"] for r in results]
    assert all(s == 200 for s in statuses), f"evaluate encountered error: {results}"

    fired_counts = []
    skipped_counts = []
    event_ids = set()
    for res in results:
        body = res.get("body") or {}
        if isinstance(body, dict):
            fired_counts.append(body.get("escalations_fired", 0))
            skipped_counts.append(body.get("skipped_idempotent", 0))

    # One call fires the escalation; the other sees the existing event and skips.
    assert sum(fired_counts) == 1, f"expected exactly one escalation fired across both calls: {results}"
    assert sum(skipped_counts) == 1, f"expected exactly one idempotent skip across both calls: {results}"

    # Event history pagination must work and surface the reason.
    with TestClient(app) as c2:
        events = c2.get(
            f"{ESCALATIONS_BASE}/events",
            headers=headers,
            params={"entity_id": issue_id, "limit": 10, "skip": 0},
        )
        assert events.status_code == 200
        payload = events.json()
        assert len(payload) == 1
        assert payload[0]["reason"]["condition_type"] == "time_in_state"

        paged = c2.get(
            f"{ESCALATIONS_BASE}/events",
            headers=headers,
            params={"limit": 1, "skip": 0},
        )
        assert paged.status_code == 200
        assert len(paged.json()) <= 1


def test_spot_check_permissions_and_audit_logs_for_state_changes(client, tmp_path):
    from datetime import UTC, datetime, timedelta

    app, engine, _ = _make_app(tmp_path)
    ISSUES_BASE = "/api/v1/compliance/issues"
    TASKS_BASE = "/api/v1/tasks"
    ESCALATIONS_BASE = "/api/v1/compliance/escalation-policies"

    with TestClient(app) as c:
        owner = _bootstrap_org_user(c)
        owner_headers = _headers(owner[0], owner[1])
        owner_user_id = _org_user_id_from_token(c, owner[0])

        # Create a read-only user in the same org.
        ro_email = f"ro-{uuid.uuid4().hex[:8]}@example.com"
        ro_register = c.post(
            "/api/v1/auth/register",
            json={"email": ro_email, "password": "Pass1234!@", "organization_name": "ro-org"},
        )
        assert ro_register.status_code == 200, ro_register.text
        ro_token = ro_register.json()["access_token"]
        invite = c.post(
            "/api/v1/memberships",
            headers=owner_headers,
            json={"email": ro_email, "role_name": "readonly", "status": "active"},
        )
        assert invite.status_code == 201, invite.text
        ro_headers = _headers(ro_token, owner[1])

        # Permission codes on changed endpoints are enforced.
        task = c.post(TASKS_BASE, headers=owner_headers, json={"title": "Permission check"})
        assert task.status_code == 201
        task_id = task.json()["id"]
        assert c.post(f"{TASKS_BASE}/{task_id}/complete", headers=ro_headers, json={}).status_code == 403
        assert c.post(f"{TASKS_BASE}/{task_id}/cancel", headers=ro_headers, json={"cancellation_reason": "no"}).status_code == 403

        issue = c.post(
            ISSUES_BASE,
            headers=owner_headers,
            json={
                "title": "Permission issue",
                "description": "desc",
                "issue_type": "custom",
                "severity": "medium",
                "source_type": "manual",
                "owner_id": owner_user_id,
            },
        )
        assert issue.status_code == 201
        issue_id = issue.json()["id"]
        assert c.post(
            f"{ISSUES_BASE}/{issue_id}/transition", headers=ro_headers, json={"new_status": "investigating"}
        ).status_code == 403
        assert c.post(
            f"{ESCALATIONS_BASE}/evaluate", headers=ro_headers
        ).status_code == 403

        # Owner performs state-changing actions.
        c.post(f"{TASKS_BASE}/{task_id}/complete", headers=owner_headers, json={})
        c.post(f"{TASKS_BASE}/{task_id}/cancel", headers=owner_headers, json={"cancellation_reason": "audit"})
        c.post(f"{ISSUES_BASE}/{issue_id}/transition", headers=owner_headers, json={"new_status": "investigating"})

        # Escalation action with a backdated issue so the policy fires immediately.
        esc_issue = c.post(
            ISSUES_BASE,
            headers=owner_headers,
            json={
                "title": "Stuck escalation",
                "description": "desc",
                "issue_type": "custom",
                "severity": "critical",
                "source_type": "manual",
                "owner_id": owner_user_id,
            },
        )
        assert esc_issue.status_code == 201
        esc_issue_id = esc_issue.json()["id"]
        from sqlalchemy import update
        from app.models.issue import Issue as IssueModel
        with engine.begin() as conn:
            conn.execute(
                update(IssueModel)
                .where(IssueModel.id == uuid.UUID(esc_issue_id))
                .values(updated_at=datetime.now(UTC) - timedelta(hours=5))
            )
        policy = c.post(
            ESCALATIONS_BASE,
            headers=owner_headers,
            json={
                "name": "Stuck >2h audit",
                "entity_type": "issue",
                "condition_type": "time_in_state",
                "condition_value": {"hours": 2},
                "escalate_to_user_id": owner_user_id,
                "notification_message_template": "Escalation {entity_type} {entity_id} by {condition_type}",
            },
        )
        assert policy.status_code == 201
        evaluate = c.post(f"{ESCALATIONS_BASE}/evaluate", headers=owner_headers)
        assert evaluate.status_code == 200

        # RCA action follows issue resolution.
        for state in ["mitigating", "resolved"]:
            r = c.post(f"{ISSUES_BASE}/{issue_id}/transition", headers=owner_headers, json={"new_status": state})
            assert r.status_code == 200
        rca = c.post(
            f"{ISSUES_BASE}/{issue_id}/rca",
            headers=owner_headers,
            json={
                "summary": "Audit RCA",
                "timeline_description": "Timeline",
                "root_cause": "Cause",
                "contributing_factors": [],
                "corrective_actions": [],
                "preventive_measures": [],
            },
        )
        assert rca.status_code == 201

        # Audit log records the state changes.
        logs = c.get("/api/v1/audit-logs", headers=owner_headers)
        assert logs.status_code == 200
        actions = {entry["action"] for entry in logs.json()}
        assert "task.completed" in actions
        assert "task.cancelled" in actions
        assert "issue.transitioned" in actions
        assert "escalation.fired" in actions
        assert "rca.created" in actions
