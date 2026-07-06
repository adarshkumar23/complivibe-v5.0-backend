import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceBotSubscription(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_bot_subscriptions"
    __table_args__ = (
        CheckConstraint("platform IN ('slack','teams')", name="ck_compliance_bot_subscriptions_platform"),
        UniqueConstraint("organization_id", "user_id", "platform", name="uq_compliance_bot_subscriptions_org_user_platform"),
        Index("ix_compliance_bot_subscriptions_org_platform", "organization_id", "platform"),
        Index("ix_compliance_bot_subscriptions_org_active", "organization_id", "is_active"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    channel_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    digest_time_utc: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    sla_alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_digest_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sla_alert_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
