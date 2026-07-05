import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class RegulatoryChangeAlert(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "regulatory_change_alerts"
    __table_args__ = (
        UniqueConstraint("organization_id", "source_key", "source_item_id", "framework_code", name="uq_reg_alert_org_source_item_fw"),
        Index("ix_reg_alerts_org_status_detected", "organization_id", "status", "detected_at"),
        Index("ix_reg_alerts_source_status", "source_key", "status"),
        Index("ix_reg_alerts_framework_detected", "framework_code", "detected_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    source_key: Mapped[str] = mapped_column(String(80), nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    framework_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_item_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
