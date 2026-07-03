from __future__ import annotations

import uuid

from sqlalchemy import Select, desc, select
from sqlalchemy.orm import Session

from app.models.scheduler_run_log import SchedulerRunLog


class SchedulerAdminService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_job_status(self, scheduler=None) -> list[dict]:
        jobs = []
        if scheduler is not None:
            jobs = list(scheduler.get_jobs())

        rows = self.db.execute(
            select(SchedulerRunLog).order_by(desc(SchedulerRunLog.started_at))
        ).scalars().all()
        latest_by_job: dict[str, SchedulerRunLog] = {}
        for row in rows:
            if row.job_name not in latest_by_job:
                latest_by_job[row.job_name] = row

        payload: list[dict] = []
        for job in jobs:
            latest = latest_by_job.get(job.id)
            payload.append(
                {
                    "job_id": job.id,
                    "next_run_time": getattr(job, "next_run_time", None),
                    "trigger_description": str(job.trigger),
                    "last_run_at": latest.started_at if latest else None,
                    "last_status": latest.status if latest else None,
                    "last_records_processed": latest.records_processed if latest else None,
                }
            )

        if not payload:
            try:
                from app.core.pbc_scheduler import SCHEDULER_JOB_IDS

                for job_id in SCHEDULER_JOB_IDS:
                    latest = latest_by_job.get(job_id)
                    payload.append(
                        {
                            "job_id": job_id,
                            "next_run_time": None,
                            "trigger_description": "scheduler_not_running",
                            "last_run_at": latest.started_at if latest else None,
                            "last_status": latest.status if latest else None,
                            "last_records_processed": latest.records_processed if latest else None,
                        }
                    )
            except Exception:
                pass
        return payload

    def get_run_history(
        self,
        *,
        job_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[SchedulerRunLog]:
        stmt: Select[tuple[SchedulerRunLog]] = select(SchedulerRunLog)
        if job_name is not None:
            stmt = stmt.where(SchedulerRunLog.job_name == job_name)
        if status is not None:
            stmt = stmt.where(SchedulerRunLog.status == status)
        stmt = stmt.order_by(SchedulerRunLog.started_at.desc()).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def get_run_log(self, log_id: uuid.UUID) -> SchedulerRunLog:
        row = self.db.execute(select(SchedulerRunLog).where(SchedulerRunLog.id == log_id)).scalar_one_or_none()
        if row is None:
            from fastapi import HTTPException, status

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler run log not found")
        return row
