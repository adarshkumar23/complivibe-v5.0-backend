from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.models.scheduler_run_log import SchedulerRunLog


class SchedulerJobLogger:
    @staticmethod
    def run_logged(
        job_name: str,
        job_fn: Callable[..., dict[str, Any] | None],
        db_session_factory: Callable[[], Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        db = db_session_factory()
        log = SchedulerRunLog(
            job_name=job_name,
            started_at=datetime.now(UTC),
            status="running",
        )
        db.add(log)
        db.commit()
        try:
            result = job_fn(db=db, **kwargs)
            records = result.get("records_processed", None) if isinstance(result, dict) else None
            log.status = "completed"
            log.completed_at = datetime.now(UTC)
            log.records_processed = records
            db.commit()
            return result or {}
        except Exception as exc:
            log.status = "failed"
            log.completed_at = datetime.now(UTC)
            log.error_message = str(exc)[:1000]
            db.commit()
            raise
        finally:
            db.close()

