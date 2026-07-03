import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIContentDraft(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_content_drafts"
    __table_args__ = (
        CheckConstraint("content_type IN ('policy', 'control', 'risk')", name="ck_ai_draft_content_type"),
        CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_ai_draft_provider"),
        CheckConstraint("status IN ('draft', 'accepted', 'discarded')", name="ck_ai_draft_status"),
        Index("ix_ai_draft_org_status", "organization_id", "status"),
        Index("ix_ai_draft_org_bu", "organization_id", "business_unit_id"),
    )

    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_input: Mapped[str] = mapped_column(Text, nullable=False)
    draft_output: Mapped[str] = mapped_column(Text, nullable=False)
    provider_used: Mapped[str] = mapped_column(String(20), nullable=False)
    used_byo_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    linked_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "compliance_policies.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_content_drafts_linked_policy_id",
        ),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
