import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class RateLimitConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rate_limit_configs"
    __table_args__ = (
        CheckConstraint(
            "endpoint_group IN ('api_general', 'ingest', 'auth', 'reports', 'public', 'ai_governance', 'scim')",
            name="ck_rate_limit_configs_endpoint_group",
        ),
        UniqueConstraint("organization_id", "endpoint_group", name="uq_rate_limit_configs_org_group"),
        Index("ix_rate_limit_configs_org_group_active", "organization_id", "endpoint_group", "is_active"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    endpoint_group: Mapped[str] = mapped_column(String(50), nullable=False)
    requests_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_per_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    requests_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    burst_allowance: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
