import uuid

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.compliance.services.scheduler_admin_service import SchedulerAdminService
from app.core.deps import get_current_active_user, get_db, require_permission
from app.models.membership import Membership
from app.models.user import User
from app.schemas.scheduler_admin import SchedulerJobStatusRead, SchedulerRunLogRead

router = APIRouter(prefix="/admin/scheduler", tags=["scheduler-admin"])


def _run_log_read(row) -> SchedulerRunLogRead:
    return SchedulerRunLogRead(
        id=row.id,
        job_name=row.job_name,
        started_at=row.started_at,
        completed_at=row.completed_at,
        status=row.status,
        records_processed=row.records_processed,
        error_message=row.error_message,
        created_at=row.created_at,
    )


@router.get("/jobs", response_model=list[SchedulerJobStatusRead])
def get_scheduler_jobs(
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Membership = Depends(require_permission("scheduler:admin")),
) -> list[SchedulerJobStatusRead]:
    scheduler = getattr(request.app.state, "pbc_scheduler", None)
    rows = SchedulerAdminService(db).get_job_status(scheduler)
    return [SchedulerJobStatusRead(**row) for row in rows]


@router.get("/runs", response_model=list[SchedulerRunLogRead])
def get_scheduler_runs(
    job_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Membership = Depends(require_permission("scheduler:admin")),
) -> list[SchedulerRunLogRead]:
    rows = SchedulerAdminService(db).get_run_history(job_name=job_name, status=status, limit=limit)
    return [_run_log_read(row) for row in rows]


@router.get("/runs/{log_id}", response_model=SchedulerRunLogRead)
def get_scheduler_run_log(
    log_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
    __: Membership = Depends(require_permission("scheduler:admin")),
) -> SchedulerRunLogRead:
    row = SchedulerAdminService(db).get_run_log(log_id)
    return _run_log_read(row)

