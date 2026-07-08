import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ApplicabilityEvaluationRun(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "applicability_evaluation_runs"
    __table_args__ = (
        Index("ix_app_eval_runs_org_framework", "organization_id", "framework_id"),
        Index("ix_app_eval_runs_org_status", "organization_id", "status"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_obligations_count: Mapped[int] = mapped_column(nullable=False, default=0)
    applicable_count: Mapped[int] = mapped_column(nullable=False, default=0)
    not_applicable_count: Mapped[int] = mapped_column(nullable=False, default=0)
    needs_review_count: Mapped[int] = mapped_column(nullable=False, default=0)
    unknown_count: Mapped[int] = mapped_column(nullable=False, default=0)
    states_updated_count: Mapped[int] = mapped_column(nullable=False, default=0)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
