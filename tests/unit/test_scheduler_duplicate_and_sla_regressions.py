"""Regressions for two P0 scheduler defects found 2026-07-19.

1. Duplicate execution. `register_pbc_scheduler` starts a BackgroundScheduler in
   every gunicorn worker, so a 2-worker deployment ran all 33 jobs twice per
   tick (observed in production as paired scheduler_run_logs rows ~110ms apart).
   `SchedulerJobLogger.run_logged` now *claims* each tick: the check for a
   recent/in-flight run and the insert of the "running" row happen atomically
   under `pg_advisory_xact_lock`, so the second worker is refused.

   A duration-held mutex was tried first and measured failing: fast jobs
   (compound_insight_reactive_drain completes in ~6ms) finish and release before
   the sibling worker contends, which then acquires cleanly and runs the same
   tick anyway. The duplicate being fixed is sequential, not overlapping.

2. `issue_sla_breach_check` had failed 314/314 times since inception with
   "'UUID' object has no attribute 'id'": `select(Organization.id)` with
   `.scalars()` yields UUIDs, not ORM rows, so `row.id` always raised. The job
   had therefore never once performed an SLA breach check in production.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.scheduler_lock import (
    DEFAULT_DEDUPE_WINDOW,
    STALE_RUNNING_AFTER,
    advisory_key,
    claim_job_tick,
)
from app.core.scheduler_logger import SchedulerJobLogger
from app.models.issue import Issue
from app.models.issue_sla_tracking import IssueSLATracking
from app.models.organization import Organization
from app.models.scheduler_run_log import SchedulerRunLog
from app.models.user import User


# --------------------------------------------------------------------------
# 1. Duplicate scheduler execution
# --------------------------------------------------------------------------

def test_advisory_key_is_stable_and_fits_signed_bigint():
    a, b = advisory_key("issue_sla_breach_check"), advisory_key("issue_sla_breach_check")
    assert a == b, "key must be stable across calls or the lock never matches"
    assert advisory_key("job_a") != advisory_key("job_b"), "distinct jobs must not share a key"
    for name in ("email_outbox_flush", "pbc_overdue_daily_sweep", "x" * 200):
        assert -(2**63) <= advisory_key(name) < 2**63, "must fit a Postgres signed bigint"


def test_claim_succeeds_on_non_postgres(db_session):
    """SQLite has no advisory locks; those runs are single-process, so never block."""
    assert claim_job_tick(db_session, "sqlite_job") is not None


def test_second_claim_in_same_window_is_refused(db_session):
    """The core regression: a *sequential* duplicate must be refused.

    The first design held a lock for the job's duration, which did not help --
    compound_insight_reactive_drain finishes in ~6ms, so the second worker
    simply acquired after the first released and ran the same tick again.
    """
    first = claim_job_tick(db_session, "dupe_job")
    assert first is not None
    first.status = "completed"
    first.completed_at = datetime.now(UTC)
    db_session.commit()

    # Second worker fires ~100ms later, after the first already finished.
    assert claim_job_tick(db_session, "dupe_job") is None

    rows = db_session.execute(
        select(SchedulerRunLog).where(SchedulerRunLog.job_name == "dupe_job")
    ).scalars().all()
    assert len(rows) == 1, "a refused claim must not write a second run row"


def test_claim_refused_while_a_run_is_still_in_flight(db_session):
    """A long job must not be started again by another worker mid-run."""
    first = claim_job_tick(db_session, "slow_job")
    assert first is not None and first.status == "running"
    assert claim_job_tick(db_session, "slow_job") is None


def test_claim_allowed_again_after_the_dedupe_window(db_session):
    """A genuine later tick must still run."""
    first = claim_job_tick(db_session, "later_job")
    assert first is not None
    first.status = "completed"
    first.completed_at = datetime.now(UTC)
    first.started_at = datetime.now(UTC) - timedelta(minutes=5)
    db_session.commit()

    assert claim_job_tick(db_session, "later_job") is not None, (
        "the dedupe window must not suppress the next real tick"
    )


def test_stale_running_row_does_not_block_the_job_forever(db_session):
    """A worker killed mid-run must not disable its job permanently.

    The in-flight check refuses a claim while a `running` row exists. Without an
    age bound, a single hard-killed worker would strand that row and every
    subsequent tick would be refused forever.
    """
    stranded = SchedulerRunLog(
        job_name="stranded_job",
        started_at=datetime.now(UTC) - (STALE_RUNNING_AFTER + timedelta(minutes=5)),
        status="running",
    )
    db_session.add(stranded)
    db_session.commit()

    claim = claim_job_tick(db_session, "stranded_job")
    assert claim is not None, "an abandoned running row must not block the job forever"

    db_session.refresh(stranded)
    assert stranded.status == "failed"
    assert "Abandoned" in (stranded.error_message or "")


def test_recent_running_row_still_blocks(db_session):
    """A genuinely in-flight run must still refuse a concurrent claim."""
    fresh = SchedulerRunLog(
        job_name="inflight_job", started_at=datetime.now(UTC), status="running"
    )
    db_session.add(fresh)
    db_session.commit()
    assert claim_job_tick(db_session, "inflight_job") is None


def test_stale_threshold_exceeds_real_job_durations():
    """Longest observed production job is ~35s (vendor_kyb_rescreen_sweep)."""
    assert STALE_RUNNING_AFTER > timedelta(minutes=5)


def test_dedupe_window_is_shorter_than_the_shortest_schedule():
    """Guards the invariant the window depends on (shortest job interval = 5min)."""
    assert DEFAULT_DEDUPE_WINDOW < timedelta(minutes=5)


def test_skipped_run_writes_no_scheduler_run_log(db_session, monkeypatch):
    """A tick lost to another worker must leave no log row."""
    import app.core.scheduler_logger as mod

    monkeypatch.setattr(mod, "claim_job_tick", lambda db, job_name: None)

    calls: list[int] = []

    def _job(*, db):
        calls.append(1)
        return {"records_processed": 1}

    before = len(db_session.execute(select(SchedulerRunLog)).scalars().all())
    result = SchedulerJobLogger.run_logged(
        job_name="contended_job", job_fn=_job, db_session_factory=lambda: db_session
    )
    after = len(db_session.execute(select(SchedulerRunLog)).scalars().all())

    assert result.get("skipped") is True
    assert calls == [], "the job body must not run when another worker claimed the tick"
    assert after == before


def test_uncontended_run_still_logs_and_executes(db_session):
    """The claim must not change behaviour when nothing else is contending."""

    def _job(*, db):
        return {"records_processed": 7}

    result = SchedulerJobLogger.run_logged(
        job_name="uncontended_job", job_fn=_job, db_session_factory=lambda: db_session
    )
    assert result["records_processed"] == 7
    row = db_session.execute(
        select(SchedulerRunLog).where(SchedulerRunLog.job_name == "uncontended_job")
    ).scalars().one()
    assert row.status == "completed"
    assert row.records_processed == 7


def test_failed_job_still_records_terminal_status(db_session):
    def _job(*, db):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        SchedulerJobLogger.run_logged(
            job_name="failing_job", job_fn=_job, db_session_factory=lambda: db_session
        )
    row = db_session.execute(
        select(SchedulerRunLog).where(SchedulerRunLog.job_name == "failing_job")
    ).scalars().one()
    assert row.status == "failed"
    assert "boom" in row.error_message


# --------------------------------------------------------------------------
# 2. issue_sla_breach_check
# --------------------------------------------------------------------------

def _make_breached_issue(db_session) -> tuple[Organization, Issue]:
    org = Organization(id=uuid.uuid4(), name="SLA Org", slug=f"sla-org-{uuid.uuid4().hex[:8]}")
    db_session.add(org)
    owner = User(
        id=uuid.uuid4(),
        email=f"sla-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        full_name="SLA Owner",
        is_active=True,
    )
    db_session.add(owner)
    db_session.flush()

    issue = Issue(
        id=uuid.uuid4(),
        organization_id=org.id,
        title="Overdue issue",
        description="d",
        issue_type="compliance_violation",
        severity="critical",
        status="open",
        owner_id=owner.id,
        created_by=owner.id,
    )
    db_session.add(issue)
    db_session.flush()

    past = datetime.now(UTC) - timedelta(hours=6)
    db_session.add(
        IssueSLATracking(
            id=uuid.uuid4(),
            organization_id=org.id,
            issue_id=issue.id,
            response_deadline=past,
            resolution_deadline=past,
            response_breached=False,
            resolution_breached=False,
        )
    )
    db_session.commit()
    return org, issue


def test_sla_job_does_not_raise_on_uuid_org_ids(db_session):
    """The exact production failure: `row.id` on a UUID from .scalars()."""
    from app.core.pbc_scheduler import _run_issue_sla_breach_check_job_internal

    _make_breached_issue(db_session)
    # Before the fix this raised AttributeError: 'UUID' object has no attribute 'id'.
    result = _run_issue_sla_breach_check_job_internal(db=db_session)
    assert isinstance(result, dict)


def test_sla_job_actually_detects_and_flags_breaches(db_session):
    """Not just 'does not crash' -- it must do the work it was silently skipping."""
    from app.core.pbc_scheduler import _run_issue_sla_breach_check_job_internal

    org, issue = _make_breached_issue(db_session)
    result = _run_issue_sla_breach_check_job_internal(db=db_session)

    assert result["response_breached"] >= 1
    assert result["resolution_breached"] >= 1

    tracking = db_session.execute(
        select(IssueSLATracking).where(IssueSLATracking.issue_id == issue.id)
    ).scalars().one()
    assert tracking.response_breached is True
    assert tracking.resolution_breached is True


def test_sla_job_is_idempotent_across_ticks(db_session):
    """Already-flagged breaches must not be re-counted or re-notified every hour."""
    from app.core.pbc_scheduler import _run_issue_sla_breach_check_job_internal

    _make_breached_issue(db_session)
    first = _run_issue_sla_breach_check_job_internal(db=db_session)
    second = _run_issue_sla_breach_check_job_internal(db=db_session)

    assert first["response_breached"] >= 1
    assert second["response_breached"] == 0, "a second tick must not re-flag the same breach"
    assert second["resolution_breached"] == 0
