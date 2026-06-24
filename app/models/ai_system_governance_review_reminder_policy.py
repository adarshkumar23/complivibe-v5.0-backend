import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceReviewReminderPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_review_reminder_policies"
    __table_args__ = (
        Index("ix_ai_sys_gov_review_reminder_policies_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_review_reminder_policies_org_review_type", "organization_id", "review_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    review_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    days_before_due: Mapped[int] = mapped_column(nullable=False, default=0)
    overdue_after_days: Mapped[int] = mapped_column(nullable=False, default=0)
    escalation_after_days: Mapped[int] = mapped_column(nullable=False, default=0)
    notify_assignee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
