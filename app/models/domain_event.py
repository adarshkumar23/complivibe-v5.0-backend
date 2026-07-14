import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DomainEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Persisted, append-only record of every event published on the in-process
    EventBus. This is the durable audit trail of cross-domain signal flow -- it
    does NOT replace AuditService.write_audit_log (which records the resulting
    state changes); the two are complementary. Rows are immutable: there is no
    update or delete path for domain_events, consistent with the audit-log
    pattern (ADR-004/008).
    """

    __tablename__ = "domain_events"
    __table_args__ = (
        # Common query pattern: an org's recent events of a given type.
        Index("ix_domain_events_org_type_occurred", "organization_id", "event_type", "occurred_at"),
        # Trace a whole cascade of related events by correlation_id.
        Index("ix_domain_events_correlation", "correlation_id"),
    )

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)

    payload_json: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
    )
    previous_value: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    new_value: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    triggered_by: Mapped[str] = mapped_column(String(64), nullable=False)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
