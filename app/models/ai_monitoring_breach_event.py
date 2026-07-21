import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin
from app.models.ai_monitoring_config import THRESHOLD_OPERATORS, _sql_in


class AIMonitoringBreachEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """One compliance decision, per breached tier (migration 0322).

    Before this, an AI-monitoring breach left only
    `ai_monitoring_readings.within_threshold = false` plus a ControlMonitoringAlert
    whose link back to the config was untyped JSON. Neither can answer "which tier
    fired, against which obligation, and what did we do about it?".

    One row per (reading, tier), enforced by a unique index: a reading that breaches
    three tiers produces three rows, and no tier can be recorded twice.

    Both operands of the comparison are frozen onto the row alongside the obligation
    the decision was taken under. A later edit to the config must not retroactively
    rewrite the history of decisions already made. Numeric(10,4) rather than Float, and
    matching ai_monitoring_readings.value exactly, so a stored decision can never
    disagree with a recomputation of it at the fourth decimal place.
    """

    __tablename__ = "ai_monitoring_breach_events"
    __table_args__ = (
        CheckConstraint(
            f"threshold_operator IN ({_sql_in(THRESHOLD_OPERATORS)})",
            name="ck_ai_monitoring_breach_events_operator",
        ),
        Index("uq_ai_monitoring_breach_events_reading_tier", "reading_id", "tier", unique=True),
        Index(
            "ix_ai_monitoring_breach_events_org_system_decided",
            "organization_id",
            "ai_system_id",
            "decided_at",
        ),
        Index("ix_ai_monitoring_breach_events_obligation", "obligation_id"),
    )

    reading_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_monitoring_readings.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: deleting a threshold config must not erase the record of
    # decisions already made under it. Those decisions happened.
    config_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_monitoring_configs.id", ondelete="RESTRICT"), nullable=False
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False
    )
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="warning")
    escalation_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    observed_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    threshold_operator: Mapped[str] = mapped_column(String(8), nullable=False)

    # Frozen alongside the operands, and for the same reason. Nullable because a
    # threshold may not have been obligation-linked at the moment it fired.
    obligation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("obligations.id", ondelete="SET NULL"), nullable=True
    )

    # Deliberately NOT CHECK-constrained: this records what was actually dispatched at
    # the time, and an audit record must stay valid even if that workflow value is
    # later removed from the config vocabulary.
    workflow_triggered: Mapped[str] = mapped_column(String(32), nullable=False)
    # Only known after dispatch succeeds. A dispatch failure must not lose the record
    # that core decided a breach occurred.
    workflow_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)

    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    decided_by: Mapped[str] = mapped_column(
        String(64), nullable=False, default="core.compliance_event_bridge"
    )
