import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIGuardrailEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_guardrail_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('check_passed', 'violation_detected', 'blocked')",
            name="ck_ai_guardrail_events_type",
        ),
        Index("ix_ai_guardrail_events_org_system_created", "organization_id", "ai_system_id", "created_at"),
        Index("ix_ai_guardrail_events_org_guardrail_created", "organization_id", "guardrail_id", "created_at"),
    )

    guardrail_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_policy_guardrails.id", ondelete="CASCADE"), nullable=False)
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
