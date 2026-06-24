import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OscalExportJob(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "oscal_export_jobs"
    __table_args__ = (
        CheckConstraint(
            "export_type IN ('ssp', 'assessment_plan', 'assessment_results', 'full_package')",
            name="ck_oscal_export_jobs_export_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'complete', 'failed')",
            name="ck_oscal_export_jobs_status",
        ),
        Index("ix_oscal_export_jobs_org_status", "organization_id", "status"),
        Index("ix_oscal_export_jobs_org_type_created", "organization_id", "export_type", "created_at"),
    )

    export_type: Mapped[str] = mapped_column(String(20), nullable=False)
    framework_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    oscal_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1.2")

    # JSON used for sqlite test compatibility while Postgres stores JSONB via migration.
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
