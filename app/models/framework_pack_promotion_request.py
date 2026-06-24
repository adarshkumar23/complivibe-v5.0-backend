import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkPackPromotionRequest(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_pack_promotion_requests"
    __table_args__ = (
        Index("ix_framework_pack_promotions_org_framework", "organization_id", "framework_id"),
        Index("ix_framework_pack_promotions_org_status", "organization_id", "status"),
        Index("ix_framework_pack_promotions_org_requested", "organization_id", "requested_at"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    framework_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_coverage_level: Mapped[str] = mapped_column(String(32), nullable=False)
    to_coverage_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
