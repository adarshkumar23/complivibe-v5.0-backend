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
            "status IN ('open', 'in_remediation', 'remediated', 'closed', 'risk_accepted', 'remediation_in_progress', 'resolved', 'accepted_risk')",
            name="ck_audit_findings_status",
        ),
        CheckConstraint(
            "finding_type IN ('observation', 'minor_nonconformity', 'major_nonconformity', 'opportunity_for_improvement')",
            name="ck_audit_findings_finding_type",
        ),
        UniqueConstraint("organization_id", "finding_ref", name="uq_audit_findings_org_ref"),
        Index("ix_audit_findings_org_engagement", "organization_id", "audit_engagement_id"),
        Index("ix_audit_findings_org_audit_id", "organization_id", "audit_id"),
        Index("ix_audit_findings_org_status_severity", "organization_id", "status", "severity"),
        Index("ix_audit_findings_org_status", "organization_id", "status"),
        Index("ix_audit_findings_org_severity", "organization_id", "severity"),
        Index("ix_audit_findings_control_id", "control_id"),
        Index("ix_audit_findings_org_assigned_owner", "organization_id", "assigned_owner_id"),
    )

    # legacy -> kept for backward compatibility
    audit_engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    # v2 canonical field
    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_ref: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(50), nullable=False, default="observation")
    framework_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # legacy -> kept for backward compatibility
    assigned_owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # v2 canonical field
    remediation_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # legacy -> kept for backward compatibility
    remediation_action: Mapped[str] = mapped_column(Text, nullable=False)
    # v2 canonical field
    remediation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    # legacy -> kept for backward compatibility
    target_remediation_date: Mapped[date] = mapped_column(Date, nullable=False)
    # v2 canonical field
    remediation_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    # legacy -> kept for backward compatibility
    risk_register_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # v2 canonical field
    linked_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
