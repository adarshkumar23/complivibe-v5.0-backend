import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Issue(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issues"
    __table_args__ = (
        CheckConstraint(
            "issue_type IN ('security_incident', 'compliance_violation', 'operational_failure', 'vendor_failure', 'data_loss', 'unauthorized_access', 'policy_violation', 'custom')",
            name="ck_issues_issue_type",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_issues_severity",
        ),
        CheckConstraint(
            # Keep in sync with ISSUE_SOURCE_TYPES in app/schemas/issue.py.
            "source_type IN ('manual', 'monitoring_alert', 'audit_finding', 'vendor_assessment', 'external_report', 'data_incident', 'risk_assessment')",
            name="ck_issues_source_type",
        ),
        CheckConstraint(
            "status IN ('open', 'investigating', 'mitigating', 'resolved', 'closed')",
            name="ck_issues_status",
        ),
        Index("ix_issues_org_status", "organization_id", "status"),
        Index("ix_issues_org_severity", "organization_id", "severity"),
        Index("ix_issues_org_issue_type", "organization_id", "issue_type"),
        Index("ix_issues_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_issues_org_owner", "organization_id", "owner_id"),
        Index("ix_issues_created_at", "created_at"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
