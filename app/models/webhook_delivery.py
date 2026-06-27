import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class WebhookDelivery(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'delivered', 'failed', 'skipped')", name="ck_webhook_deliveries_status"),
        Index("ix_webhook_deliveries_org_status", "organization_id", "status"),
        Index("ix_webhook_deliveries_endpoint_status", "endpoint_id", "status"),
        Index("ix_webhook_deliveries_status_created", "status", "created_at"),
    )

    endpoint_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
