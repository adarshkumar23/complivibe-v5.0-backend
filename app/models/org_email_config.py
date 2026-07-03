import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OrgEmailConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "org_email_configs"
    __table_args__ = (
        CheckConstraint("provider IN ('ses')", name="ck_org_email_configs_provider"),
        UniqueConstraint("organization_id", name="uq_org_email_configs_org"),
        Index("ix_org_email_configs_org_active", "organization_id", "is_active"),
    )

    # Legacy fields retained for compatibility with existing privacy email-config flows.
    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="ses")
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    test_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # New per-org SES configuration fields.
    use_platform_ses: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    aws_access_key_id_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    aws_secret_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    aws_region: Mapped[str | None] = mapped_column(String(20), nullable=True, default="ap-south-1")
    from_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reply_to_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    daily_send_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    sent_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_today_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
