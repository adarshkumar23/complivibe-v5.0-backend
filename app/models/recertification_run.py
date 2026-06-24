import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RecertificationRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "recertification_runs"
    __table_args__ = (
        Index("ix_recert_run_org_type", "organization_id", "run_type"),
        Index("ix_recert_run_org_status", "organization_id", "status"),
        Index("ix_recert_run_org_created", "organization_id", "created_at"),
    )

    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("evidence_recertification_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_count: Mapped[int] = mapped_column(nullable=False, default=0)
    overdue_count: Mapped[int] = mapped_column(nullable=False, default=0)
    task_count: Mapped[int] = mapped_column(nullable=False, default=0)
    email_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skipped_duplicate_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(nullable=False, default=0)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
