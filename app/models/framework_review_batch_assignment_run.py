import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkReviewBatchAssignmentRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_review_batch_assignment_runs"
    __table_args__ = (
        Index("ix_framework_review_batch_assignment_runs_org_status", "organization_id", "status"),
        Index("ix_framework_review_batch_assignment_runs_org_plan_hash", "organization_id", "plan_hash"),
        Index("ix_framework_review_batch_assignment_runs_org_created", "organization_id", "created_at"),
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="validated")
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmation_text: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cancellation_requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancellation_request_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "framework_review_batch_cancellation_requests.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_framework_review_batch_assignment_runs_cancellation_request_id",
        ),
        nullable=True,
    )
    total_items: Mapped[int] = mapped_column(nullable=False, default=0)
    created_assignments_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skipped_items_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_items_count: Mapped[int] = mapped_column(nullable=False, default=0)
    notify_assignees: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
