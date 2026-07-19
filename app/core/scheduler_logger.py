from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.core.scheduler_lock import claim_job_tick


class SchedulerJobLogger:
    @staticmethod
    def run_logged(
        job_name: str,
        job_fn: Callable[..., dict[str, Any] | None],
        db_session_factory: Callable[[], Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        db = db_session_factory()
        try:
            # Every gunicorn worker runs its own BackgroundScheduler, so without a
            # claim each job executes once per worker. claim_job_tick writes the
            # "running" row itself, so a tick lost to another worker leaves no
            # scheduler_run_logs entry and the run count stays the true number of
            # executions.
            log = claim_job_tick(db, job_name)
            if log is None:
                return {"skipped": True, "reason": "tick_already_claimed"}

            try:
                result = job_fn(db=db, **kwargs)
                records = result.get("records_processed", None) if isinstance(result, dict) else None
                log.status = "completed"
                log.completed_at = datetime.now(UTC)
                log.records_processed = records
                db.commit()
                return result or {}
            except Exception as exc:
                # The job may have left the session in a failed transaction; roll
                # back so the terminal status can actually be written.
                db.rollback()
                log.status = "failed"
                log.completed_at = datetime.now(UTC)
                log.error_message = str(exc)[:1000]
                db.commit()
                raise
        finally:
            db.close()
