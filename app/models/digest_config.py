import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DigestConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "digest_configs"
    __table_args__ = (
        CheckConstraint("digest_type IN ('daily', 'weekly')", name="ck_digest_configs_digest_type"),
        CheckConstraint("send_day_of_week IS NULL OR (send_day_of_week >= 0 AND send_day_of_week <= 6)", name="ck_digest_configs_send_day_of_week"),
        UniqueConstraint("organization_id", "user_id", "digest_type", name="uq_digest_configs_org_user_type"),
        Index("ix_digest_configs_org_type_enabled", "organization_id", "digest_type", "is_enabled"),
        Index("ix_digest_configs_user_type", "user_id", "digest_type"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    digest_type: Mapped[str] = mapped_column(String(10), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    send_time_utc: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    send_day_of_week: Mapped[int | None] = mapped_column(nullable=True)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
