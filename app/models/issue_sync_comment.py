import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IssueSyncComment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issue_sync_comments"
    __table_args__ = (
        CheckConstraint("provider IN ('internal','jira','linear')", name="ck_issue_sync_comments_provider"),
        CheckConstraint("direction IN ('inbound','outbound')", name="ck_issue_sync_comments_direction"),
        Index("ix_issue_sync_comments_org_issue", "organization_id", "issue_id"),
        Index("ix_issue_sync_comments_org_provider", "organization_id", "provider"),
        Index(
            "uq_issue_sync_comments_issue_provider_external",
            "issue_id",
            "provider",
            "external_comment_id",
            unique=True,
            postgresql_where=text("external_comment_id IS NOT NULL"),
        ),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    external_comment_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
