"""Concurrency hardening on the two email delivery paths (2026-07-20).

Neither of these is exploitable today -- record_sent has one caller and the outbox
flush and the email worker do not currently run at the same time. Both are one added
caller away from being wrong, and both are cheap to make correct now:

  1. EmailQuotaService.record_sent did a read-modify-write (`sent_today += 1`) on an
     ORM instance. Any concurrent increment between the read and the write is lost, so
     the daily send cap silently under-counts and lets an org over-send.

  2. EmailOutboxFlushService.flush() selected pending rows with no row lock, while
     EmailWorkerService claims the very same rows with `with_for_update()`. If both
     delivery paths ever ran together the same outbox row could be sent twice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects import postgresql

from app.models.org_email_config import OrgEmailConfig
from app.platform.services.email_outbox_flush_service import EmailOutboxFlushService
from app.platform.services.email_quota_service import EmailQuotaService
from tests.helpers.auth_org import bootstrap_org_user


def _make_config(db_session, org: dict, *, limit: int = 100) -> OrgEmailConfig:
    config = OrgEmailConfig(
        organization_id=uuid.UUID(org["organization_id"]),
        created_by=uuid.UUID(org["user_id"]),
        config_json="{}",
        daily_send_limit=limit,
        sent_today=0,
        # A live window, so a send counted inside it is not discarded by a rollover.
        sent_today_reset_at=datetime.now(UTC) + timedelta(hours=24),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(config)
    db_session.commit()
    return config


def test_record_sent_does_not_lose_a_concurrent_increment(client, db_session):
    """The lost-update itself: another writer bumps the counter after this session has
    already loaded the row. A read-modify-write overwrites their increment; an atomic
    UPDATE composes with it."""
    org = bootstrap_org_user(client, email_prefix="quota-lost-update")
    org_id = uuid.UUID(org["organization_id"])
    # Held for the whole test on purpose. SQLAlchemy's identity map holds only weak
    # references, so without a live reference the stale instance can be collected and
    # silently re-read from the database -- which hides the lost update behind a GC
    # detail. A real request holds the row for the duration of the send; so does this.
    config = _make_config(db_session, org)

    service = EmailQuotaService(db_session)
    # Load the row into this session (what a caller does before deciding to send).
    assert service.check_quota(org_id) == (True, None)
    assert config.sent_today == 0

    # Meanwhile, a second writer records a send against the same row. This session's
    # identity map still believes sent_today is 0.
    # Core-level, on the raw connection: no ORM session synchronisation, so this
    # session's identity map keeps its stale sent_today -- which is precisely what
    # another process's write looks like from here.
    db_session.connection().execute(
        update(OrgEmailConfig.__table__)
        .where(OrgEmailConfig.__table__.c.organization_id == org_id)
        .values(sent_today=OrgEmailConfig.__table__.c.sent_today + 1)
    )

    assert config.sent_today == 0, "premise: this session has not seen the other write"

    service.record_sent(org_id)
    db_session.commit()

    db_session.expire_all()
    sent_today = db_session.execute(
        select(OrgEmailConfig.sent_today).where(OrgEmailConfig.organization_id == org_id)
    ).scalar_one()
    assert sent_today == 2, "record_sent must add to the stored counter, not overwrite it from a stale read"


def test_record_sent_still_counts_normally_and_still_trips_the_cap(client, db_session):
    org = bootstrap_org_user(client, email_prefix="quota-normal")
    org_id = uuid.UUID(org["organization_id"])
    _make_config(db_session, org, limit=3)

    service = EmailQuotaService(db_session)
    for _ in range(3):
        allowed, _retry = service.check_quota(org_id)
        assert allowed is True
        service.record_sent(org_id)
    db_session.commit()

    db_session.expire_all()
    sent_today = db_session.execute(
        select(OrgEmailConfig.sent_today).where(OrgEmailConfig.organization_id == org_id)
    ).scalar_one()
    assert sent_today == 3

    allowed, retry_at = service.check_quota(org_id)
    assert allowed is False, "three sends against a limit of three must exhaust the cap"
    assert retry_at is not None


def test_record_sent_survives_a_window_reset_in_the_same_call(client, db_session):
    """The reset zeroes the counter; the increment must then land on top of the reset,
    not be clobbered by it."""
    org = bootstrap_org_user(client, email_prefix="quota-reset")
    org_id = uuid.UUID(org["organization_id"])
    config = _make_config(db_session, org)
    config.sent_today = 40
    config.sent_today_reset_at = datetime.now(UTC) - timedelta(minutes=1)  # window expired
    db_session.commit()

    EmailQuotaService(db_session).record_sent(org_id)
    db_session.commit()

    db_session.expire_all()
    sent_today = db_session.execute(
        select(OrgEmailConfig.sent_today).where(OrgEmailConfig.organization_id == org_id)
    ).scalar_one()
    assert sent_today == 1, "an expired window resets to 0 and then counts this send"


def test_record_sent_is_a_noop_for_orgs_with_no_email_config(client, db_session):
    org = bootstrap_org_user(client, email_prefix="quota-noconfig")
    org_id = uuid.UUID(org["organization_id"])
    EmailQuotaService(db_session).record_sent(org_id)  # must not raise
    db_session.commit()
    assert (
        db_session.execute(
            select(OrgEmailConfig).where(OrgEmailConfig.organization_id == org_id)
        ).scalar_one_or_none()
        is None
    )


def test_outbox_flush_claims_rows_with_a_skip_locked_row_lock(db_session):
    """flush() must claim its batch the same way EmailWorkerService does, so the two
    delivery paths cannot hand the same row to two senders.

    Asserted at the statement level against the Postgres dialect: SQLite (the unit
    harness) does not render FOR UPDATE at all, so a behavioural two-connection race
    is not observable here. What is checkable -- and what actually differs before and
    after the fix -- is whether the emitted SELECT carries the lock clause.
    """
    stmt = EmailOutboxFlushService(db_session).claim_statement(batch_size=10)
    compiled = str(stmt.compile(dialect=postgresql.dialect())).upper()
    assert "FOR UPDATE" in compiled
    assert "SKIP LOCKED" in compiled

    # ...and it selects from the outbox, i.e. the lock is on the rows that matter.
    assert "EMAIL_OUTBOX" in compiled


def test_outbox_flush_still_drains_pending_rows(client, db_session, monkeypatch):
    """Behavioural guard that adding the lock did not change what flush() selects."""
    from app.models.email_outbox import EmailOutbox

    org = bootstrap_org_user(client, email_prefix="flush-drain")
    org_id = uuid.UUID(org["organization_id"])
    row = EmailOutbox(
        organization_id=org_id,
        event_type="test",
        recipient_email="drain@example.com",
        subject="s",
        body_text="b",
        body_html="<p>b</p>",
        status="pending",
        queued_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.commit()

    service = EmailOutboxFlushService(db_session)
    monkeypatch.setattr(
        service.ses, "send_email", lambda **kwargs: {"success": True, "message_id": "mid-1"}
    )
    result = service.flush()
    db_session.commit()

    assert result["total_processed"] >= 1
    db_session.expire_all()
    assert db_session.get(EmailOutbox, row.id).status == "sent"
