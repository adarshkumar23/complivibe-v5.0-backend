from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SchedulerJobStatusRead(BaseModel):
    job_id: str
    next_run_time: datetime | None = None
    trigger_description: str
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_records_processed: int | None = None


class SchedulerRunLogRead(BaseModel):
    id: UUID
    job_name: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    records_processed: int | None = None
    error_message: str | None = None
    created_at: datetime

