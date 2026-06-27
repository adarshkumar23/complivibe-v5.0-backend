import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OpenMetadataIntegration(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "openmetadata_integrations"
    __table_args__ = (
        CheckConstraint(
            "sync_status IS NULL OR sync_status IN ('success', 'failed', 'in_progress')",
            name="ck_openmetadata_integrations_sync_status",
        ),
        UniqueConstraint("organization_id", name="uq_openmetadata_integrations_org"),
    )

    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
