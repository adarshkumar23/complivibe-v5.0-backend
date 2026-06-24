import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EmailDeliveryEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_delivery_events"
    __table_args__ = (
        Index("ix_email_delivery_events_organization_id", "organization_id"),
        Index("ix_email_delivery_events_outbox_id", "email_outbox_id"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    email_outbox_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("email_outbox.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    status_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status_to: Mapped[str | None] = mapped_column(String(32), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
