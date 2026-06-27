import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RemediationSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "remediation_suggestions"
    __table_args__ = (
        CheckConstraint("suggestion_source IN ('rule_based', 'template')", name="ck_remediation_suggestions_source"),
        Index("ix_remediation_suggestions_org_issue", "organization_id", "issue_id"),
        Index("ix_remediation_suggestions_org_applied", "organization_id", "applied"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    suggestion_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion_source: Mapped[str] = mapped_column(String(50), nullable=False, default="rule_based")
    source_key: Mapped[str] = mapped_column(String(255), nullable=False)
    applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    dismissed: Mapped[bool] = mapped_column(nullable=False, default=False)
