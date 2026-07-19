"""Cross-process de-duplication for scheduled jobs.

The app runs under gunicorn with multiple workers, and `register_pbc_scheduler`
starts a `BackgroundScheduler` inside *each* worker. Every worker's scheduler
fires the same job at the same instant, so a 2-worker deployment ran all 33
jobs twice per tick (seen in production as paired `scheduler_run_logs` rows
~110ms apart).

Why this is a *claim* and not a mutex
-------------------------------------
The obvious fix -- hold an advisory lock for the duration of the job -- does
not work, and was measured failing: `compound_insight_reactive_drain` completes
in ~6ms, so worker A had already finished and released before worker B
contended ~70ms later. B then acquired cleanly and ran the same tick again.
A duration-held mutex only prevents *overlapping* runs; the bug here is
*sequential* duplicates of one scheduled tick.

So each tick is claimed instead. A claim is: "no run of this job started within
the last `dedupe_window`, and none is currently in flight." The check and the
insert of the `running` row happen inside a single short transaction guarded by
`pg_advisory_xact_lock`, which makes the check-then-act atomic across processes
and is released by Postgres at transaction end -- it cannot leak, unlike the
session-level lock this replaces (which was observed still held minutes after
its job completed).

The dedupe window must stay below the shortest schedule interval, currently
5 minutes (`email_outbox_flush`, the compound-insight and evidence drains).

Two deliberate degradations, both fail-open, because duplicate execution is a
lesser failure than silently stopping every scheduled job:

* Non-Postgres backends (SQLite under test) have no advisory locks and are
  single-process anyway, so the claim always succeeds.
* If the claim query itself errors, the job runs.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text

from app.models.scheduler_run_log import SchedulerRunLog

logger = logging.getLogger(__name__)

# Distinguishes our keys from any other advisory-lock user in the same database.
_LOCK_NAMESPACE = "complivibe.scheduler"

# Must be shorter than the shortest job interval so a legitimate next tick is
# never mistaken for a duplicate of the previous one. The shortest interval is now
# webhook_delivery_drain at 2 minutes, so this must stay well under 120s.
DEFAULT_DEDUPE_WINDOW = timedelta(seconds=60)

# A "running" row older than this is treated as abandoned rather than in flight.
# Without this a single hard-killed worker would strand a `running` row and block
# its job forever, since the in-flight check below would keep refusing every
# subsequent claim. Measured job durations top out at ~35s
# (vendor_kyb_rescreen_sweep), so an hour is far beyond any legitimate run.
STALE_RUNNING_AFTER = timedelta(hours=1)


def advisory_key(job_name: str) -> int:
    """Map a job name to a stable signed 64-bit advisory-lock key."""
    digest = hashlib.blake2b(f"{_LOCK_NAMESPACE}:{job_name}".encode(), digest_size=8).digest()
    unsigned = int.from_bytes(digest, "big", signed=False)
    # pg_advisory_xact_lock takes a signed bigint.
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


def _is_postgres(db: Any) -> bool:
    try:
        return db.bind.dialect.name == "postgresql"
    except Exception:
        try:
            return db.get_bind().dialect.name == "postgresql"
        except Exception:
            return False


def claim_job_tick(
    db: Any,
    job_name: str,
    *,
    dedupe_window: timedelta = DEFAULT_DEDUPE_WINDOW,
) -> SchedulerRunLog | None:
    """Claim this tick for `job_name`, returning the `running` row, or None.

    None means another worker already claimed this tick (or is still running the
    job), and this process must not execute it.

    On success the returned `SchedulerRunLog` is already committed with status
    "running"; the caller owns finishing it.
    """
    now = datetime.now(UTC)
    is_pg = _is_postgres(db)

    try:
        if is_pg:
            # Transaction-scoped: released by Postgres at commit/rollback, so a
            # crashed worker cannot strand it. Serialises the check+insert below.
            db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": advisory_key(job_name)})

        recent = db.execute(
            select(SchedulerRunLog)
            .where(
                SchedulerRunLog.job_name == job_name,
                SchedulerRunLog.started_at > now - dedupe_window,
            )
            .limit(1)
        ).scalars().first()
        if recent is not None:
            db.rollback()  # releases the xact lock
            logger.info(
                "Job %s already claimed for this tick by another process; skipping", job_name
            )
            return None

        in_flight = db.execute(
            select(SchedulerRunLog)
            .where(
                SchedulerRunLog.job_name == job_name,
                SchedulerRunLog.status == "running",
                SchedulerRunLog.started_at > now - STALE_RUNNING_AFTER,
            )
            .limit(1)
        ).scalars().first()
        if in_flight is not None:
            db.rollback()
            logger.info("Job %s is still running elsewhere; skipping this tick", job_name)
            return None

        # Reclaim rows abandoned by a terminated worker so the ledger stays truthful
        # and they stop being counted as anything.
        abandoned = db.execute(
            select(SchedulerRunLog).where(
                SchedulerRunLog.job_name == job_name,
                SchedulerRunLog.status == "running",
                SchedulerRunLog.started_at <= now - STALE_RUNNING_AFTER,
            )
        ).scalars().all()
        for row in abandoned:
            row.status = "failed"
            row.completed_at = now
            row.error_message = "Abandoned: no completion recorded (worker terminated mid-run)"

        log = SchedulerRunLog(job_name=job_name, started_at=now, status="running")
        db.add(log)
        db.commit()  # releases the xact lock and publishes the claim
        return log
    except Exception:
        logger.exception(
            "Tick claim failed for %s; running unlocked (duplicate execution is preferable "
            "to skipping the job entirely)",
            job_name,
        )
        try:
            db.rollback()
        except Exception:
            pass
        log = SchedulerRunLog(job_name=job_name, started_at=now, status="running")
        db.add(log)
        db.commit()
        return log
