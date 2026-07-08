import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class IssuePolicyLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issue_policy_links"
    __table_args__ = (
        CheckConstraint("link_type IN ('violated', 'related')", name="ck_issue_policy_links_link_type"),
        Index("ix_issue_policy_links_org_issue", "organization_id", "issue_id"),
        Index("ix_issue_policy_links_org_policy", "organization_id", "policy_id"),
        Index("ix_issue_policy_links_org_policy_link_type", "organization_id", "policy_id", "link_type"),
        Index(
            "uq_issue_policy_links_issue_policy_active",
            "issue_id",
            "policy_id",
            unique=True,
            postgresql_where=text("unlinked_at IS NULL"),
            sqlite_where=text("unlinked_at IS NULL"),
        ),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(50), nullable=False)
    link_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    linked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlinked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    unlink_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
