import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class LLMObservabilityEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A single LLM observability measurement: a trace/latency poll, a hallucination check,
    a token-cost reading, or a RAG retrieval-quality evaluation for one AI system.
    """

    __tablename__ = "llm_observability_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('trace', 'hallucination_check', 'cost_reading', 'rag_evaluation')",
            name="ck_llm_observability_events_event_type",
        ),
        Index("ix_llm_observability_events_org_system", "organization_id", "ai_system_id"),
        Index("ix_llm_observability_events_org_type", "organization_id", "event_type"),
        Index("ix_llm_observability_events_org_flagged", "organization_id", "is_flagged"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_tool: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
