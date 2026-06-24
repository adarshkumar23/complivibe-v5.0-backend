import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.export_job import ExportJob
from app.models.export_job_event import ExportJobEvent


class ExportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_job(self, export_job_id: uuid.UUID) -> ExportJob | None:
        return self.db.execute(select(ExportJob).where(ExportJob.id == export_job_id)).scalar_one_or_none()

    def list_jobs(
        self,
        *,
        organization_id: uuid.UUID,
        export_type: str | None,
        status: str | None,
        framework_id: uuid.UUID | None,
        limit: int,
        offset: int,
    ) -> list[ExportJob]:
        stmt = select(ExportJob).where(ExportJob.organization_id == organization_id)
        if export_type:
            stmt = stmt.where(ExportJob.export_type == export_type)
        if status:
            stmt = stmt.where(ExportJob.status == status)
        if framework_id:
            stmt = stmt.where(ExportJob.framework_id == framework_id)
        stmt = stmt.order_by(ExportJob.created_at.desc()).offset(offset).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def list_events(self, *, organization_id: uuid.UUID, export_job_id: uuid.UUID) -> list[ExportJobEvent]:
        stmt = (
            select(ExportJobEvent)
            .where(
                ExportJobEvent.organization_id == organization_id,
                ExportJobEvent.export_job_id == export_job_id,
            )
            .order_by(ExportJobEvent.created_at.asc())
        )
        return self.db.execute(stmt).scalars().all()
