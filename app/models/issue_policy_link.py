import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
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
        UniqueConstraint("organization_id", "issue_id", "policy_id", name="uq_issue_policy_links_org_issue_policy"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(50), nullable=False)
    linked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
