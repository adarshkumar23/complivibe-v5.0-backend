import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class IssueControlLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issue_control_links"
    __table_args__ = (
        CheckConstraint(
            "failure_type IN ('control_absent', 'control_failed', 'control_bypassed', 'control_ineffective')",
            name="ck_issue_control_links_failure_type",
        ),
        Index("ix_issue_control_links_org_issue", "organization_id", "issue_id"),
        Index("ix_issue_control_links_org_control", "organization_id", "control_id"),
        Index("ix_issue_control_links_org_control_failure_type", "organization_id", "control_id", "failure_type"),
        Index("ix_issue_control_links_control_issue", "control_id", "issue_id"),
        UniqueConstraint("organization_id", "issue_id", "control_id", name="uq_issue_control_links_org_issue_control"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    failure_type: Mapped[str] = mapped_column(String(50), nullable=False)
    linked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
