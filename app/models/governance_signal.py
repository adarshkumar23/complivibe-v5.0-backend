import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceSignal(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_signals"
    __table_args__ = (
        Index("ix_governance_signals_org_domain", "organization_id", "domain"),
        Index("ix_governance_signals_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_governance_signals_org_ai_system", "organization_id", "related_ai_system_id"),
        Index("ix_governance_signals_org_assessment", "organization_id", "related_risk_assessment_id"),
        Index("ix_governance_signals_org_signal_type", "organization_id", "signal_type"),
        Index("ix_governance_signals_org_reason_code", "organization_id", "reason_code"),
        Index("ix_governance_signals_org_severity", "organization_id", "severity"),
        Index("ix_governance_signals_org_status", "organization_id", "status"),
        Index("ix_governance_signals_org_created", "organization_id", "created_at"),
    )

    domain: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    related_ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_risk_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_assessments.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_type: Mapped[str] = mapped_column(String(128), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    created_by_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolve_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dismiss_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
