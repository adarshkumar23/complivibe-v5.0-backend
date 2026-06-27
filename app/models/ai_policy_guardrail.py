import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIPolicyGuardrail(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_policy_guardrails"
    __table_args__ = (
        CheckConstraint(
            "guardrail_type IN ('data_scope', 'user_scope', 'action_scope', 'geographic_scope', 'financial_limit', 'approval_required')",
            name="ck_ai_policy_guardrails_type",
        ),
        CheckConstraint(
            "violation_action IN ('alert_only', 'block_and_alert', 'require_approval')",
            name="ck_ai_policy_guardrails_violation_action",
        ),
        Index("ix_ai_policy_guardrails_org_system_active", "organization_id", "ai_system_id", "is_active"),
        Index("ix_ai_policy_guardrails_org_active", "organization_id", "is_active"),
    )

    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True)
    guardrail_type: Mapped[str] = mapped_column(String(50), nullable=False)
    constraint_description: Mapped[str] = mapped_column(Text, nullable=False)
    constraint_value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    violation_action: Mapped[str] = mapped_column(String(20), nullable=False, default="alert_only")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
