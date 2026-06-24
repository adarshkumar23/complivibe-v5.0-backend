import uuid

from sqlalchemy import ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkReviewSLAPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_review_sla_policies"
    __table_args__ = (
        Index("ix_framework_review_sla_policies_org_status", "organization_id", "status"),
        Index("ix_framework_review_sla_policies_org_review_type", "organization_id", "review_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    review_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_coverage_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_days: Mapped[int] = mapped_column(nullable=False, default=14)
    escalation_after_days: Mapped[int] = mapped_column(nullable=False, default=7)
    reminder_before_days: Mapped[int] = mapped_column(nullable=False, default=2)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
