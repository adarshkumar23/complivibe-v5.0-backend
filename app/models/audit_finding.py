import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditFinding(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "audit_findings"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'informational')",
            name="ck_audit_findings_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'in_remediation', 'remediated', 'closed', 'risk_accepted')",
            name="ck_audit_findings_status",
        ),
        UniqueConstraint("organization_id", "finding_ref", name="uq_audit_findings_org_ref"),
        Index("ix_audit_findings_org_engagement", "organization_id", "audit_engagement_id"),
        Index("ix_audit_findings_org_status_severity", "organization_id", "status", "severity"),
        Index("ix_audit_findings_org_assigned_owner", "organization_id", "assigned_owner_id"),
    )

    audit_engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_ref: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    framework_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    remediation_action: Mapped[str] = mapped_column(Text, nullable=False)
    target_remediation_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    risk_register_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
