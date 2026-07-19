"""Scheduled webhook delivery drain.

Until this job existed, WebhookService.emit() wrote 'pending' rows from seven
services and deliver() had a single caller -- a manual per-delivery endpoint --
so nothing drained the queue.

These tests make REAL HTTP calls against a local throwaway server, because the
things worth proving here are network behaviours: that a transient failure is
retried on a LATER tick rather than dropped, that a permanently dead endpoint is
only given up on after the real cross-tick cap, that one slow endpoint cannot
occupy the scheduler thread, and that a cross-org row is refused.
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from sqlalchemy import select

from app.compliance.services.webhook_service import (
    MAX_DELIVERY_ATTEMPTS,
    WebhookService,
    run_webhook_delivery_drain,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_endpoint import WebhookEndpoint


class _Handler(BaseHTTPRequestHandler):
    behaviour = {"mode": "ok", "delay": 0.0}
    received: list[dict] = []

    def do_POST(self):  # noqa: N802
        mode = _Handler.behaviour["mode"]
        delay = float(_Handler.behaviour["delay"])
        if delay:
            time.sleep(delay)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        _Handler.received.append(
            {"path": self.path, "body": body, "signature": self.headers.get("X-CompliVibe-Signature")}
        )
        code = 200 if mode == "ok" else 500
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):  # silence
        return


@pytest.fixture
def http_server():
    _Handler.behaviour = {"mode": "ok", "delay": 0.0}
    _Handler.received = []
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, _Handler
    server.shutdown()
    server.server_close()


def _org(db, hint: str) -> Organization:
    org = Organization(id=uuid.uuid4(), name=f"WH {hint} {uuid.uuid4().hex[:6]}", slug=f"wh-{hint}-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    return org


def _endpoint(db, org, url: str) -> WebhookEndpoint:
    creator = User(
        id=uuid.uuid4(), email=f"wh-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x", full_name="WH", is_active=True,
    )
    db.add(creator)
    db.flush()
    ep = WebhookEndpoint(
        id=uuid.uuid4(), organization_id=org.id, name="ep", url=url,
        secret="s3cret", event_types=["risk.critical"], is_active=True,
        created_by=creator.id,
    )
    db.add(ep)
    db.flush()
    return ep


def _pending(db, org, ep, *, attempts: int = 0, last_attempted_at=None) -> WebhookDelivery:
    row = WebhookDelivery(
        id=uuid.uuid4(), organization_id=org.id, endpoint_id=ep.id,
        event_type="risk.critical", payload={"hello": "world"},
        payload_hash="h" * 64, signature="sha256=deadbeef",
        status="pending", attempts=attempts, last_attempted_at=last_attempted_at,
    )
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------ happy path
def test_drain_delivers_a_pending_webhook_over_real_http(db_session, http_server):
    server, handler = http_server
    url = f"http://127.0.0.1:{server.server_port}/hook"
    org = _org(db_session, "ok")
    ep = _endpoint(db_session, org, url)
    row = _pending(db_session, org, ep)

    # 127.0.0.1 is loopback, which the SSRF guard blocks by design. Point the guard
    # at a public-looking answer for this test only; the guard itself is exercised
    # in test_ssrf_* below.
    import app.compliance.services.webhook_service as mod

    original = mod.assert_public_http_url
    mod.assert_public_http_url = lambda *_a, **_k: None
    try:
        result = run_webhook_delivery_drain(db_session)
    finally:
        mod.assert_public_http_url = original

    db_session.refresh(row)
    assert result["delivered"] == 1, result
    assert row.status == "delivered"
    assert row.response_code == 200
    assert len(handler.received) == 1, "the endpoint must actually have been called"
    assert handler.received[0]["signature"] == "sha256=deadbeef", "signature header must be sent"


# ------------------------------------------------- cross-tick retry (the point)
def test_transient_failure_retries_on_a_later_tick_and_then_succeeds(db_session, http_server):
    """The behaviour the old in-call-only loop could not provide."""
    server, handler = http_server
    url = f"http://127.0.0.1:{server.server_port}/hook"
    org = _org(db_session, "transient")
    ep = _endpoint(db_session, org, url)
    row = _pending(db_session, org, ep)

    import app.compliance.services.webhook_service as mod

    original = mod.assert_public_http_url
    mod.assert_public_http_url = lambda *_a, **_k: None
    try:
        # Tick 1: endpoint is down.
        handler.behaviour["mode"] = "fail"
        first = run_webhook_delivery_drain(db_session)
        db_session.refresh(row)
        assert first["retry_scheduled"] == 1, first
        assert row.status == "pending", "a transient failure must stay retryable, not go terminal"
        assert row.attempts == 1

        # Tick 2 arrives before the backoff has elapsed -> deliberately skipped.
        skipped = run_webhook_delivery_drain(db_session)
        assert skipped["skipped_backoff"] == 1
        assert skipped["attempted"] == 0

        # Tick 3, after the backoff window, with the endpoint healthy again.
        handler.behaviour["mode"] = "ok"
        row.last_attempted_at = datetime.now(UTC) - timedelta(minutes=10)
        db_session.commit()
        third = run_webhook_delivery_drain(db_session)
    finally:
        mod.assert_public_http_url = original

    db_session.refresh(row)
    assert third["delivered"] == 1, third
    assert row.status == "delivered"
    assert row.attempts == 2, "one attempt per tick, not a burst inside one call"


def test_permanently_down_endpoint_fails_only_after_the_cross_tick_cap(db_session, http_server):
    server, handler = http_server
    url = f"http://127.0.0.1:{server.server_port}/hook"
    org = _org(db_session, "dead")
    ep = _endpoint(db_session, org, url)
    row = _pending(db_session, org, ep)
    handler.behaviour["mode"] = "fail"

    import app.compliance.services.webhook_service as mod

    original = mod.assert_public_http_url
    mod.assert_public_http_url = lambda *_a, **_k: None
    try:
        for tick in range(MAX_DELIVERY_ATTEMPTS):
            row.last_attempted_at = None  # collapse the backoff for the test
            db_session.commit()
            run_webhook_delivery_drain(db_session)
            db_session.refresh(row)
            if row.attempts < MAX_DELIVERY_ATTEMPTS:
                assert row.status == "pending", (
                    f"tick {tick}: still under the cap ({row.attempts}/{MAX_DELIVERY_ATTEMPTS}) "
                    "so it must remain retryable"
                )
    finally:
        mod.assert_public_http_url = original

    db_session.refresh(row)
    assert row.attempts == MAX_DELIVERY_ATTEMPTS
    assert row.status == "failed", "only terminal once the cap is exhausted"
    assert len(handler.received) == MAX_DELIVERY_ATTEMPTS, "one real HTTP attempt per tick"


def test_exhausted_delivery_is_not_picked_up_again(db_session, http_server):
    server, _ = http_server
    org = _org(db_session, "exhausted")
    ep = _endpoint(db_session, org, f"http://127.0.0.1:{server.server_port}/hook")
    row = _pending(db_session, org, ep, attempts=MAX_DELIVERY_ATTEMPTS)
    row.status = "failed"
    db_session.commit()

    result = run_webhook_delivery_drain(db_session)
    assert result["attempted"] == 0, "a terminally failed delivery must not be retried forever"


# ------------------------------------------------------------------ bounded work
def test_batch_cap_bounds_how_many_deliveries_one_tick_starts(db_session, http_server):
    server, handler = http_server
    url = f"http://127.0.0.1:{server.server_port}/hook"
    org = _org(db_session, "batch")
    ep = _endpoint(db_session, org, url)
    for _ in range(7):
        _pending(db_session, org, ep)

    import app.compliance.services.webhook_service as mod

    original = mod.assert_public_http_url
    mod.assert_public_http_url = lambda *_a, **_k: None
    try:
        result = run_webhook_delivery_drain(db_session, batch_limit=3)
    finally:
        mod.assert_public_http_url = original

    assert result["attempted"] == 3, result
    assert len(handler.received) == 3
    remaining = db_session.execute(
        select(WebhookDelivery).where(WebhookDelivery.status == "pending")
    ).scalars().all()
    assert len(remaining) == 4, "the rest stay queued for the next tick"


def test_time_budget_stops_a_slow_queue_from_occupying_the_worker(db_session, http_server):
    """A backlog of slow endpoints must not hold the scheduler thread."""
    server, handler = http_server
    url = f"http://127.0.0.1:{server.server_port}/hook"
    org = _org(db_session, "slow")
    ep = _endpoint(db_session, org, url)
    for _ in range(6):
        _pending(db_session, org, ep)
    handler.behaviour["delay"] = 0.4

    import app.compliance.services.webhook_service as mod

    original = mod.assert_public_http_url
    mod.assert_public_http_url = lambda *_a, **_k: None
    started = time.monotonic()
    try:
        result = run_webhook_delivery_drain(db_session, batch_limit=50, time_budget_seconds=1.0)
    finally:
        mod.assert_public_http_url = original
        handler.behaviour["delay"] = 0.0
    elapsed = time.monotonic() - started

    assert elapsed < 4.0, f"drain ran {elapsed:.1f}s -- the wall-clock budget did not bound it"
    assert result["attempted"] < 6, "the budget must stop it starting every queued delivery"
    assert result["attempted"] >= 1


# ------------------------------------------------------------------------ SSRF
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9/hook",           # loopback
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://10.0.0.5/hook",              # private range
        "file:///etc/passwd",                # non-http scheme
    ],
)
def test_internal_targets_are_refused_and_never_called(db_session, url):
    org = _org(db_session, "ssrf")
    ep = _endpoint(db_session, org, url)
    row = _pending(db_session, org, ep)

    result = run_webhook_delivery_drain(db_session)
    db_session.refresh(row)

    assert result["delivered"] == 0
    assert row.status == "failed"
    assert row.response_code is None, "an internal target must be refused before any request is made"
    assert "public http(s) URL" in (row.error_message or "")


# -------------------------------------------------------------- org isolation
def test_delivery_is_refused_when_endpoint_belongs_to_another_org(db_session, http_server):
    """Adversarial: a row pointing at ANOTHER org's endpoint must not be sent.

    emit() cannot produce this today; it is asserted so that a future bug or a
    hand-written row cannot POST one tenant's payload to another tenant's URL.
    """
    server, handler = http_server
    url = f"http://127.0.0.1:{server.server_port}/hook"
    org_a, org_b = _org(db_session, "iso-a"), _org(db_session, "iso-b")
    ep_b = _endpoint(db_session, org_b, url)

    # Delivery owned by org A, but pointing at org B's endpoint.
    row = WebhookDelivery(
        id=uuid.uuid4(), organization_id=org_a.id, endpoint_id=ep_b.id,
        event_type="risk.critical", payload={"secret": "org-a-data"},
        payload_hash="h" * 64, signature="sha256=x", status="pending", attempts=0,
    )
    db_session.add(row)
    db_session.commit()

    import app.compliance.services.webhook_service as mod

    original = mod.assert_public_http_url
    mod.assert_public_http_url = lambda *_a, **_k: None
    try:
        WebhookService(db_session).deliver(row.id, max_in_call_attempts=1)
    finally:
        mod.assert_public_http_url = original

    db_session.refresh(row)
    assert row.status == "failed"
    assert "endpoint not found" in (row.error_message or "").lower()
    assert handler.received == [], "org A's payload must never reach org B's URL"
