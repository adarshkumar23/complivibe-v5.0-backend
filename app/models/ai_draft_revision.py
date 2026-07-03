import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIDraftRevision(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_draft_revisions"
    __table_args__ = (
        CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_ai_rev_provider"),
        UniqueConstraint("draft_id", "revision_number", name="uq_ai_rev_draft_num"),
        Index("ix_ai_rev_draft", "draft_id"),
        Index("ix_ai_rev_org_created", "organization_id", "created_at"),
    )

    draft_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_content_drafts.id", ondelete="CASCADE"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    refinement_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    revised_output: Mapped[str] = mapped_column(Text, nullable=False)
    provider_used: Mapped[str] = mapped_column(String(20), nullable=False)
    used_byo_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
