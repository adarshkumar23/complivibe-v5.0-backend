import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataRetentionReview(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_retention_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'in_review', 'completed', 'waived')", name="ck_data_retention_reviews_status"),
        CheckConstraint(
            "review_type IN ('retention_expired', 'max_retention_exceeded', 'manual_review')",
            name="ck_data_retention_reviews_review_type",
        ),
        CheckConstraint("required_action IN ('flag', 'archive', 'delete')", name="ck_data_retention_reviews_required_action"),
        Index("ix_data_retention_reviews_org_status", "organization_id", "status"),
        Index("ix_data_retention_reviews_org_asset", "organization_id", "data_asset_id"),
        Index("ix_data_retention_reviews_created", "created_at"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("data_retention_policies.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)
    days_overdue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_action: Mapped[str] = mapped_column(String(20), nullable=False)
    linked_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
