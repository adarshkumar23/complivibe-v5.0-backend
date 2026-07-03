import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SiemExportConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "siem_export_configs"
    __table_args__ = (
        CheckConstraint(
            "export_format IN ('json', 'cef', 'leef', 'splunk_hec')",
            name="ck_siem_export_configs_format",
        ),
        CheckConstraint(
            "delivery_method IN ('webhook', 'syslog', 'file', 'api_pull')",
            name="ck_siem_export_configs_delivery_method",
        ),
        Index("ix_siem_export_configs_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    export_format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    delivery_method: Mapped[str] = mapped_column(String(20), nullable=False, default="webhook")
    endpoint_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    include_actions: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list)
    exclude_actions: Mapped[list] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=list)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    last_exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_export_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    export_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
