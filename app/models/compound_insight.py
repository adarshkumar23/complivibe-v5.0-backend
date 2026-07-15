import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class CompoundInsight(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A code-confirmed cross-domain compound exposure surfaced as one insight.

    The detection is deterministic (the source of truth). ``templated_narrative``
    is always present; the AI-upgraded narrative (headline/summary/actions) is a
    best-effort enrichment recorded only when the Groq call succeeds and validates.
    Deduplicated by (organization_id, dedup_key).
    """

    __tablename__ = "compound_insights"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_compound_insights_severity",
        ),
        CheckConstraint(
            "status IN ('surfaced', 'auto_resolved')",
            name="ck_compound_insights_status",
        ),
        CheckConstraint(
            "narrative_source IN ('template', 'ai')",
            name="ck_compound_insights_narrative_source",
        ),
        UniqueConstraint("organization_id", "dedup_key", name="uq_compound_insights_org_dedup"),
        Index("ix_compound_insights_org_status", "organization_id", "status"),
        Index("ix_compound_insights_org_pattern", "organization_id", "pattern_id"),
    )

    pattern_id: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="surfaced")
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)

    templated_narrative: Mapped[str] = mapped_column(Text, nullable=False)
    narrative_source: Mapped[str] = mapped_column(String(16), nullable=False, default="template")
    narrative_headline: Mapped[str | None] = mapped_column(String(300), nullable=True)
    narrative_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_actions_json: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    matched_nodes_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )

    provider_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    used_byo_credentials: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    detection_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CompoundInsightCandidate(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A node flagged (by the Phase 1 event bus, flush-only) for compound re-check.

    The listener writes these cheaply inside the publisher's transaction; the
    APScheduler drain processes unprocessed rows (traversal + AI) in its OWN
    committed session, so no DB transaction is ever held across the AI call.
    """

    __tablename__ = "compound_insight_candidates"
    __table_args__ = (
        Index("ix_compound_insight_candidates_pending", "organization_id", "processed_at"),
        Index("ix_compound_insight_candidates_entity", "organization_id", "entity_type", "entity_id"),
    )

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    flagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
