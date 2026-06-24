import uuid
from datetime import UTC, datetime, timedelta

from app.models.email_outbox import EmailOutbox


def _register(client, email: str, password: str, org_name: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "organization_name": org_name},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str, org_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if org_id:
        headers["X-Organization-ID"] = org_id
    return headers


def _get_org_id(client, token: str) -> str:
    response = client.get("/api/v1/organizations/me", headers=_headers(token))
    assert response.status_code == 200
    return response.json()[0]["id"]


def _get_template_id(client, token: str, org_id: str, template_key: str) -> str:
    templates = client.get("/api/v1/email/templates", headers=_headers(token, org_id))
    assert templates.status_code == 200
    template = next(t for t in templates.json() if t["template_key"] == template_key)
    return str(template["id"])


def _queue_email(client, token: str, org_id: str, template_id: str, recipient: str = "worker@example.com") -> str:
    response = client.post(
        "/api/v1/email/outbox",
        headers=_headers(token, org_id),
        json={
            "template_id": template_id,
            "recipient_email": recipient,
            "event_type": "worker.test",
            "variables_json": {"user_name": "Worker", "task_title": "Process"},
        },
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def test_worker_claim_and_complete_with_locking_and_events(client):
    owner = _register(client, "p15-owner1@example.com", "Pass1234!@", "P15 Org1")
    org_id = _get_org_id(client, owner)
    template_id = _get_template_id(client, owner, org_id, "task_assigned")
    email_id = _queue_email(client, owner, org_id, template_id)

    claim = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-a", "limit": 10},
    )
    assert claim.status_code == 200
    assert len(claim.json()) == 1
    claimed = claim.json()[0]
    assert claimed["id"] == email_id
    assert claimed["status"] == "processing"
    assert claimed["locked_by"] == "worker-a"
    assert claimed["lock_expires_at"] is not None

    second_claim = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-b", "limit": 10},
    )
    assert second_claim.status_code == 200
    assert second_claim.json() == []

    mismatch_complete = client.post(
        f"/api/v1/email/worker/{email_id}/complete",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-b"},
    )
    assert mismatch_complete.status_code == 403

    complete = client.post(
        f"/api/v1/email/worker/{email_id}/complete",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-a"},
    )
    assert complete.status_code == 200
    completed = complete.json()["email"]
    assert completed["status"] == "sent"
    assert completed["locked_by"] is None
    assert completed["lock_expires_at"] is None

    detail = client.get(f"/api/v1/email/outbox/{email_id}", headers=_headers(owner, org_id))
    assert detail.status_code == 200
    event_types = [e["event_type"] for e in detail.json()["delivery_events"]]
    assert "email.claimed" in event_types
    assert "email.worker_completed" in event_types

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id))
    assert logs.status_code == 200
    actions = [a["action"] for a in logs.json()]
    assert "email.worker_completed" in actions


def test_worker_fail_retry_and_dead_letter(client, db_session):
    owner = _register(client, "p15-owner2@example.com", "Pass1234!@", "P15 Org2")
    org_id = _get_org_id(client, owner)
    template_id = _get_template_id(client, owner, org_id, "task_assigned")

    # Retry path
    email_retry = _queue_email(client, owner, org_id, template_id, recipient="retry@example.com")
    claim_retry = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-r", "limit": 10},
    )
    assert any(item["id"] == email_retry for item in claim_retry.json())

    mismatch_fail = client.post(
        f"/api/v1/email/worker/{email_retry}/fail",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-other", "error_message": "x" * 5},
    )
    assert mismatch_fail.status_code == 403

    fail_retry = client.post(
        f"/api/v1/email/worker/{email_retry}/fail",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-r", "error_message": "worker failed", "retry_after_seconds": 60},
    )
    assert fail_retry.status_code == 200
    failed_email = fail_retry.json()["email"]
    assert failed_email["status"] == "failed"
    assert failed_email["attempt_count"] == 1
    assert failed_email["next_attempt_at"] is not None

    # Dead-letter path
    email_dead = _queue_email(client, owner, org_id, template_id, recipient="dead@example.com")
    claim_dead = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-d", "limit": 10},
    )
    assert any(item["id"] == email_dead for item in claim_dead.json())

    for i in range(1, 4):
        fail = client.post(
            f"/api/v1/email/worker/{email_dead}/fail",
            headers=_headers(owner, org_id),
            json={"worker_id": "worker-d", "error_message": f"fail-{i}", "retry_after_seconds": 1},
        )
        assert fail.status_code == 200
        if i < 3:
            row = db_session.query(EmailOutbox).filter(EmailOutbox.id == uuid.UUID(email_dead)).one()
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
            db_session.commit()
            re_claim = client.post(
                "/api/v1/email/worker/claim",
                headers=_headers(owner, org_id),
                json={"worker_id": "worker-d", "limit": 10},
            )
            assert any(item["id"] == email_dead for item in re_claim.json())

    final_detail = client.get(f"/api/v1/email/outbox/{email_dead}", headers=_headers(owner, org_id))
    assert final_detail.status_code == 200
    assert final_detail.json()["status"] == "dead_letter"

    claim_after_dead = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner, org_id),
        json={"worker_id": "worker-d", "limit": 50},
    )
    assert claim_after_dead.status_code == 200
    assert not any(item["id"] == email_dead for item in claim_after_dead.json())

    event_types = [e["event_type"] for e in final_detail.json()["delivery_events"]]
    assert "email.worker_failed" in event_types
    assert "email.dead_lettered" in event_types

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner, org_id))
    actions = [a["action"] for a in logs.json()]
    assert "email.worker_failed" in actions
    assert "email.dead_lettered" in actions


def test_release_expired_locks_and_non_claimable_statuses_and_tenant_scope(client, db_session):
    owner1 = _register(client, "p15-owner3@example.com", "Pass1234!@", "P15 Org3")
    owner2 = _register(client, "p15-owner4@example.com", "Pass1234!@", "P15 Org4")
    org1 = _get_org_id(client, owner1)
    org2 = _get_org_id(client, owner2)
    template1 = _get_template_id(client, owner1, org1, "task_assigned")

    # Cross-tenant scope: owner2 cannot claim owner1 email
    email_org1 = _queue_email(client, owner1, org1, template1, recipient="tenant@example.com")
    cross_claim = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner2, org2),
        json={"worker_id": "worker-tenant", "limit": 10},
    )
    assert cross_claim.status_code == 200
    assert cross_claim.json() == []

    # Claim in the right tenant then force expired lock and release it.
    claim = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner1, org1),
        json={"worker_id": "worker-lock", "limit": 10},
    )
    assert any(item["id"] == email_org1 for item in claim.json())

    row = db_session.query(EmailOutbox).filter(EmailOutbox.id == uuid.UUID(email_org1)).one()
    row.lock_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()

    released = client.post("/api/v1/email/worker/release-expired-locks", headers=_headers(owner1, org1))
    assert released.status_code == 200
    assert released.json()["released_count"] >= 1
    released_email = next(item for item in released.json()["emails"] if item["id"] == email_org1)
    assert released_email["status"] == "failed"

    detail = client.get(f"/api/v1/email/outbox/{email_org1}", headers=_headers(owner1, org1))
    events = [e["event_type"] for e in detail.json()["delivery_events"]]
    assert "email.expired_lock_released" in events

    # Non-claimable statuses
    email_cancel = _queue_email(client, owner1, org1, template1, recipient="cancel@example.com")
    cancel_resp = client.post(f"/api/v1/email/outbox/{email_cancel}/cancel", headers=_headers(owner1, org1))
    assert cancel_resp.status_code == 200

    email_sent = _queue_email(client, owner1, org1, template1, recipient="sent@example.com")
    sent_resp = client.post(f"/api/v1/email/outbox/{email_sent}/mark-sent", headers=_headers(owner1, org1))
    assert sent_resp.status_code == 200

    email_dead = _queue_email(client, owner1, org1, template1, recipient="dead-manual@example.com")
    dead_resp = client.post(
        f"/api/v1/email/worker/{email_dead}/dead-letter",
        headers=_headers(owner1, org1),
        json={"reason": "manual dead-letter"},
    )
    assert dead_resp.status_code == 200

    claim_after = client.post(
        "/api/v1/email/worker/claim",
        headers=_headers(owner1, org1),
        json={"worker_id": "worker-final", "limit": 100},
    )
    ids = {item["id"] for item in claim_after.json()}
    assert email_cancel not in ids
    assert email_sent not in ids
    assert email_dead not in ids

    logs = client.get("/api/v1/audit-logs", headers=_headers(owner1, org1))
    actions = [a["action"] for a in logs.json()]
    assert "email.dead_lettered" in actions
    assert "email.expired_lock_released" in actions
