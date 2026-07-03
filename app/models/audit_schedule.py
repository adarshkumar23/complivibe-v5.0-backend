import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditSchedule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "audit_schedules"
    __table_args__ = (
        CheckConstraint(
            "audit_type IN ('internal_readiness', 'external_certification', 'surveillance', 'gap_assessment')",
            name="ck_audit_schedules_audit_type",
        ),
        CheckConstraint(
            "recurrence_pattern IN ('annual', 'semi_annual', 'quarterly', 'monthly')",
            name="ck_audit_schedules_recurrence_pattern",
        ),
        CheckConstraint(
            "recurrence IN ('monthly', 'quarterly', 'semi_annual', 'annual')",
            name="ck_audit_sched_recur",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'cancelled')",
            name="ck_audit_schedules_status",
        ),
        CheckConstraint(
            "preparation_reminder_days BETWEEN 7 AND 90",
            name="ck_audit_schedules_preparation_reminder_days",
        ),
        Index("ix_audit_schedules_org_status", "organization_id", "status"),
        Index("ix_audit_schedules_org_framework", "organization_id", "framework_id"),
        Index("ix_audit_schedules_next_date_status", "next_audit_date", "status"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    audit_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    framework_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="RESTRICT"), nullable=True)
    recurrence_pattern: Mapped[str] = mapped_column(String(50), nullable=False)
    recurrence: Mapped[str] = mapped_column(String(20), nullable=False, default="annual")
    next_audit_date: Mapped[date] = mapped_column(Date, nullable=False)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    preparation_reminder_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    assigned_lead_auditor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    last_reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_audit_engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
