import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExternalSyncEvent(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "external_sync_events"
    __table_args__ = (
        CheckConstraint("provider IN ('jira','linear')", name="ck_external_sync_events_provider"),
        CheckConstraint("direction IN ('inbound','outbound')", name="ck_external_sync_events_direction"),
        CheckConstraint("entity_type IN ('issue')", name="ck_external_sync_events_entity_type"),
        CheckConstraint("status IN ('processed','failed','ignored')", name="ck_external_sync_events_status"),
        Index("ix_external_sync_events_org_connection", "organization_id", "connection_id"),
        Index("ix_external_sync_events_org_provider", "organization_id", "provider"),
        Index("ix_external_sync_events_processed_at", "processed_at"),
        Index(
            "uq_external_sync_events_connection_external_event",
            "connection_id",
            "external_event_id",
            unique=True,
            postgresql_where=text("external_event_id IS NOT NULL AND direction = 'inbound'"),
        ),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("external_sync_connections.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="issue")
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processed")
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
