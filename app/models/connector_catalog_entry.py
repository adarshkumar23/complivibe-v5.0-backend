import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ConnectorCatalogEntry(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "connector_catalog_entries"
    __table_args__ = (
        UniqueConstraint("name", name="uq_connector_catalog_entries_name"),
        Index("ix_connector_catalog_entries_category", "category"),
        Index("ix_connector_catalog_entries_enabled", "enabled"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConnectorOrgEnablement(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "connector_org_enablements"
    __table_args__ = (
        UniqueConstraint("organization_id", "connector_id", name="uq_connector_enablement_org_connector"),
        Index("ix_connector_enablements_org_enabled", "organization_id", "enabled"),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("connector_catalog_entries.id", ondelete="CASCADE"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Credential-shaped fields (token/secret/password/key -- see
    # ConnectorMarketplaceService.sensitive_field_names) are encrypted at rest via the vault
    # transit backend (app.services.secrets_service.SecretsService) before being stored here;
    # non-sensitive fields (e.g. file_format, taxonomy) are stored as plain values.
    config_values_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # connection_status reflects config_schema shape validation, and -- when the connector's
    # config_schema declares a network-target field (base_url/instance_url/org_url/etc.) -- a
    # real outbound HTTP probe of that target (see ConnectorMarketplaceService.test_connection).
    # Values: "unconfigured" (never validated), "validated" (schema satisfied and, if a network
    # target field exists, it responded), "invalid" (config fails schema), "unreachable" (schema
    # ok but the live HTTP probe failed -- DNS/refused/timeout), "disconnected" (explicitly
    # disabled).
    connection_status: Mapped[str] = mapped_column(String(20), nullable=False, default="unconfigured")
    connection_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connection_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
