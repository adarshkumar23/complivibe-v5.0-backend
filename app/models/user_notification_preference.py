import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class UserNotificationPreference(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "user_notification_preferences"
    __table_args__ = (
        CheckConstraint("channel IN ('email', 'in_app', 'none')", name="ck_user_notification_preferences_channel"),
        CheckConstraint(
            "min_severity IS NULL OR min_severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_user_notification_preferences_min_severity",
        ),
        UniqueConstraint(
            "organization_id",
            "user_id",
            "notification_type",
            name="uq_user_notification_preferences_org_user_type",
        ),
        Index("ix_user_notification_preferences_org_user", "organization_id", "user_id"),
        Index(
            "ix_user_notification_preferences_user_type_enabled",
            "user_id",
            "notification_type",
            "is_enabled",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(100), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    min_severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
