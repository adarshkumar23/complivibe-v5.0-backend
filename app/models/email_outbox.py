import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EmailOutbox(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        Index("ix_email_outbox_organization_id", "organization_id"),
        Index("ix_email_outbox_status", "status"),
        Index("ix_email_outbox_event_type", "event_type"),
        Index("ix_email_outbox_recipient_email", "recipient_email"),
        Index("ix_email_outbox_next_attempt_at", "next_attempt_at"),
        Index("ix_email_outbox_lock_expires_at", "lock_expires_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("email_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    template_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    template_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lock_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ses_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(nullable=False, default=0)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    worker_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
