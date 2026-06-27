import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class IssueTransition(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issue_transitions"
    __table_args__ = (
        Index("ix_issue_transitions_issue_id", "issue_id"),
        Index("ix_issue_transitions_org_issue", "organization_id", "issue_id"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str] = mapped_column(String(50), nullable=False)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
