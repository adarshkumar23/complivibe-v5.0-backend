import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditEngagement(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "audit_engagements"
    __table_args__ = (
        CheckConstraint(
            "audit_type IN ('internal_readiness', 'external_certification', 'surveillance', 'gap_assessment')",
            name="ck_audit_engagements_audit_type",
        ),
        CheckConstraint(
            "status IN ('planning', 'fieldwork', 'review', 'report_issuance', 'closed', 'cancelled')",
            name="ck_audit_engagements_status",
        ),
        CheckConstraint("end_date >= start_date", name="ck_audit_engagements_date_range"),
        Index("ix_audit_engagements_org_status", "organization_id", "status"),
        Index("ix_audit_engagements_org_audit_type", "organization_id", "audit_type"),
        Index("ix_audit_engagements_org_start_date", "organization_id", "start_date"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    audit_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_framework_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    assigned_auditor_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="planning")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    report_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lead_auditor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audit_firm: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("audit_schedules.id", ondelete="SET NULL"), nullable=True
    )
