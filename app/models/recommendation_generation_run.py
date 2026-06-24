import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RecommendationGenerationRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "recommendation_generation_runs"
    __table_args__ = (
        Index("ix_reco_run_org_framework", "organization_id", "framework_id"),
        Index("ix_reco_run_org_status", "organization_id", "status"),
        Index("ix_reco_run_org_created", "organization_id", "created_at"),
    )

    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("frameworks.id", ondelete="SET NULL"),
        nullable=True,
    )
    dry_run: Mapped[bool] = mapped_column(nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evaluated_obligations_count: Mapped[int] = mapped_column(nullable=False, default=0)
    recommendations_created_count: Mapped[int] = mapped_column(nullable=False, default=0)
    recommendations_skipped_duplicate_count: Mapped[int] = mapped_column(nullable=False, default=0)
    recommendations_would_create_count: Mapped[int] = mapped_column(nullable=False, default=0)
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
