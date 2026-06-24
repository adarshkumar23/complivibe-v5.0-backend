import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PolicyIssueLink(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_issue_links"
    __table_args__ = (
        CheckConstraint(
            "violation_type IN ('violation', 'near_miss', 'observation', 'procedural_gap')",
            name="ck_policy_issue_links_violation_type",
        ),
        CheckConstraint(
            "severity_impact IN ('low', 'medium', 'high', 'critical')",
            name="ck_policy_issue_links_severity_impact",
        ),
        Index("ix_policy_issue_links_org_policy", "organization_id", "policy_id"),
        Index("ix_policy_issue_links_org_issue", "organization_id", "issue_id"),
        Index("ix_policy_issue_links_org_violation_type", "organization_id", "violation_type"),
        Index("ix_policy_issue_links_org_deleted_at", "organization_id", "deleted_at"),
        Index(
            "uq_policy_issue_links_policy_issue_active",
            "policy_id",
            "issue_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("compliance_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    issue_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    violation_type: Mapped[str] = mapped_column(String(50), nullable=False, default="violation")
    severity_impact: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
