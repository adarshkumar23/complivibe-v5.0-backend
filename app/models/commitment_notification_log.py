import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class CommitmentNotificationLog(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "commitment_notification_log"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('reminder', 'triggered', 'escalation', 'fulfilled')",
            name="ck_commitment_notification_log_notification_type",
        ),
        CheckConstraint(
            "triggered_by IN ('scheduler', 'manual', 'api')",
            name="ck_commitment_notification_log_triggered_by",
        ),
        Index("ix_commitment_notification_log_commitment_id", "commitment_id"),
        Index("ix_commitment_notification_log_org_queued_at", "organization_id", "queued_at"),
    )

    commitment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("customer_commitments.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    recipient_user_ids: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    message_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False)
