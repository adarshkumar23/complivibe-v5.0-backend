import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorMitigationCase(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_mitigation_cases"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_vendor_mitigation_cases_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'pending_vendor_evidence', 'under_review', 'closed', 'escalated', 'cancelled')",
            name="ck_vendor_mitigation_cases_status",
        ),
        CheckConstraint(
            "assessment_id IS NOT NULL OR ai_assessment_id IS NOT NULL",
            name="ck_vendor_mitigation_cases_assessment_required",
        ),
        Index("ix_vendor_mitigation_cases_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_mitigation_cases_org_status_severity", "organization_id", "status", "severity"),
        Index("ix_vendor_mitigation_cases_due_status", "due_date", "status"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendor_assessments.id", ondelete="SET NULL"), nullable=True)
    ai_assessment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ai_vendor_assessments.id", ondelete="SET NULL"), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    assigned_owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    closure_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    escalated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
