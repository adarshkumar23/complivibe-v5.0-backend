import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class FrameworkReviewerWorkloadSnapshot(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_reviewer_workload_snapshots"
    __table_args__ = (
        Index("ix_framework_reviewer_workload_snapshots_org_user", "organization_id", "user_id"),
        Index("ix_framework_reviewer_workload_snapshots_org_calculated", "organization_id", "calculated_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    active_assignments: Mapped[int] = mapped_column(nullable=False, default=0)
    accepted_assignments: Mapped[int] = mapped_column(nullable=False, default=0)
    overdue_assignments: Mapped[int] = mapped_column(nullable=False, default=0)
    completed_assignments_last_30d: Mapped[int] = mapped_column(nullable=False, default=0)
    open_escalations: Mapped[int] = mapped_column(nullable=False, default=0)
    workload_score: Mapped[int] = mapped_column(nullable=False, default=0)
    capacity_remaining: Mapped[int | None] = mapped_column(nullable=True)
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
