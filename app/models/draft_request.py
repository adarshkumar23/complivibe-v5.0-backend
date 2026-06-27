import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DraftRequest(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "draft_requests"
    __table_args__ = (
        CheckConstraint(
            "draft_type IN ('policy_content', 'risk_description', 'control_description', 'evidence_description', 'rca_summary', 'ai_risk_assessment_narrative', 'model_card_content', 'eu_act_conformity_narrative', 'ai_policy_draft')",
            name="ck_draft_requests_draft_type",
        ),
        Index("ix_draft_requests_org_draft_type", "organization_id", "draft_type"),
        Index("ix_draft_requests_org_created_by", "organization_id", "created_by"),
        Index("ix_draft_requests_org_applied", "organization_id", "applied"),
    )

    draft_type: Mapped[str] = mapped_column(String(50), nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    draft_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
