import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceReviewRecurrenceTemplate(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_review_recurrence_templates"
    __table_args__ = (
        Index("ix_ai_sys_gov_review_recur_templates_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_review_recur_templates_org_review_type", "organization_id", "review_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cadence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    interval_value: Mapped[int] = mapped_column(nullable=False, default=1)
    default_reminder_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_review_reminder_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_checklist_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    default_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
