import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceBotOutbox(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_bot_outbox"
    __table_args__ = (
        CheckConstraint(
            "message_type IN ('command_response','daily_digest','sla_alert')",
            name="ck_compliance_bot_outbox_type",
        ),
        CheckConstraint(
            "status IN ('pending','sent','failed')",
            name="ck_compliance_bot_outbox_status",
        ),
        Index("ix_compliance_bot_outbox_org_status", "organization_id", "status"),
        Index("ix_compliance_bot_outbox_org_type", "organization_id", "message_type"),
        Index("ix_compliance_bot_outbox_subscription", "subscription_id", "scheduled_for"),
    )

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("compliance_bot_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    command_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
