import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExternalSyncLink(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "external_sync_links"
    __table_args__ = (
        CheckConstraint("entity_type IN ('issue')", name="ck_external_sync_links_entity_type"),
        UniqueConstraint(
            "connection_id",
            "entity_type",
            "internal_entity_id",
            name="uq_external_sync_links_connection_internal",
        ),
        UniqueConstraint(
            "connection_id",
            "entity_type",
            "external_entity_id",
            name="uq_external_sync_links_connection_external",
        ),
        Index("ix_external_sync_links_org_connection", "organization_id", "connection_id"),
    )

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("external_sync_connections.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="issue")
    internal_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    external_entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
