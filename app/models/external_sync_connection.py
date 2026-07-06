import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExternalSyncConnection(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "external_sync_connections"
    __table_args__ = (
        CheckConstraint("provider IN ('jira','linear')", name="ck_external_sync_connections_provider"),
        CheckConstraint(
            "direction_mode IN ('outbound_only','inbound_only','two_way')",
            name="ck_external_sync_connections_direction",
        ),
        CheckConstraint("entity_type IN ('issue')", name="ck_external_sync_connections_entity_type"),
        Index("ix_external_sync_connections_org_provider", "organization_id", "provider"),
        Index("ix_external_sync_connections_org_active", "organization_id", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, default="issue")
    direction_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="two_way")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    project_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    api_base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    credentials_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_mapping_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
