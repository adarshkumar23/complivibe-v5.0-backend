import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AiGuardrailCheckEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """One row per check-action call evaluated against a derived guardrail
    (patent P3).

    Distinct from the human-authored feature's `ai_guardrail_events` monitoring
    table (migration 0128): this records the allow/deny enforcement decision for
    an agent action, the safe action *envelope* (never the payload -- see
    envelope.py), and a pointer to the signed receipt stored in
    `ai_guardrail_receipts`.
    """

    __tablename__ = "ai_guardrail_check_events"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'deny')",
            name="ck_ai_guardrail_check_events_decision",
        ),
        Index(
            "ix_ai_guardrail_check_events_org_system_created",
            "organization_id",
            "ai_system_id",
            "created_at",
        ),
        Index(
            "ix_ai_guardrail_check_events_org_guardrail",
            "organization_id",
            "guardrail_id",
        ),
    )

    guardrail_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_derived_guardrails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_envelope_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    receipt_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    evaluation_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
