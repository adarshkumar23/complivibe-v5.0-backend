import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceAutomationRule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_automation_rules"
    __table_args__ = (
        CheckConstraint(
            "trigger_source IN ('webhook','email','form')",
            name="ck_evidence_automation_rules_source",
        ),
        Index("ix_evidence_automation_rules_org_source", "organization_id", "trigger_source"),
        Index("ix_evidence_automation_rules_org_active", "organization_id", "is_active"),
    )

    trigger_source: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    target_control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    transform_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Health/telemetry columns so stale or repeatedly-failing connectors can be
    # surfaced instead of silently going dark.
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trigger_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvidenceAutomationIngestEvent(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Records every ingest event processed for a rule so retried webhook/email/form
    deliveries can be deduplicated by idempotency key rather than creating duplicate
    evidence, and so ingest history is available for troubleshooting connector health.
    """

    __tablename__ = "evidence_automation_ingest_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created','duplicate','error')",
            name="ck_evidence_automation_ingest_events_status",
        ),
        Index("ix_evidence_automation_ingest_events_org_rule", "organization_id", "automation_rule_id"),
        Index(
            "uq_evidence_automation_ingest_events_rule_key",
            "automation_rule_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    automation_rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_automation_rules.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
