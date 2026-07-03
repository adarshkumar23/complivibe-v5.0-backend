import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BreachNotification(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "breach_notifications"
    __table_args__ = (
        CheckConstraint(
            "breach_type IN ('personal_data', 'financial', 'health', 'confidential')",
            name="ck_breach_notifications_breach_type",
        ),
        CheckConstraint(
            "regulatory_framework IN ('gdpr', 'dora', 'nis2', 'hipaa', 'ccpa', 'dpdp') OR regulatory_framework IS NULL",
            name="ck_breach_notifications_regulatory_framework",
        ),
        CheckConstraint(
            "status IN ('assessing', 'notification_due', 'regulator_notified', 'subjects_notified', 'closed')",
            name="ck_breach_notifications_status",
        ),
        Index("ix_breach_notifications_org_status", "organization_id", "status"),
        Index("ix_breach_notifications_deadline_status", "regulatory_notification_deadline", "status"),
        Index("ix_breach_notifications_org_issue", "organization_id", "issue_id"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, unique=True)
    breach_type: Mapped[str] = mapped_column(String(50), nullable=False)
    personal_data_affected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    estimated_affected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regulatory_notification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regulatory_framework: Mapped[str | None] = mapped_column(String(50), nullable=True, default="gdpr")
    regulatory_notification_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=72)
    regulatory_notification_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supervisory_authority: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regulatory_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subject_notification_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subjects_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    data_subjects_affected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    special_category_data_involved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    article33_notification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    article34_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    subjects_notification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    dpa_reference_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="assessing")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
