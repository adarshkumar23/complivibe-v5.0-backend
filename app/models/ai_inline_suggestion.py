import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIInlineSuggestion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_inline_suggestions"
    __table_args__ = (
        CheckConstraint("content_type IN ('policy', 'control', 'risk')", name="ck_ai_sugg_content_type"),
        CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_ai_sugg_provider"),
        CheckConstraint("status IN ('pending', 'applied', 'dismissed')", name="ck_ai_sugg_status"),
        Index("ix_ai_sugg_org_type", "organization_id", "content_type"),
        Index("ix_ai_sugg_org_status", "organization_id", "status"),
        Index("ix_ai_sugg_org_bu", "organization_id", "business_unit_id"),
    )

    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggestions_json: Mapped[list[dict]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    linked_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    provider_used: Mapped[str] = mapped_column(String(20), nullable=False)
    used_byo_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
