import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class BillingEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "billing_events"
    __table_args__ = (
        UniqueConstraint("razorpay_event_id", name="uq_billing_events_razorpay_event_id"),
        Index("ix_billing_events_org_event", "organization_id", "event_type"),
        Index("ix_billing_events_processed_created", "processed", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    razorpay_event_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
