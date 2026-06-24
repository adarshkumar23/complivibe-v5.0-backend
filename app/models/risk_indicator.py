import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RiskIndicator(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "risk_indicators"
    __table_args__ = (
        Index("ix_risk_indicators_org_active", "organization_id", "is_active"),
        Index("ix_risk_indicators_org_metric_type", "organization_id", "metric_type"),
        Index("ix_risk_indicators_org_status", "organization_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_type: Mapped[str] = mapped_column(String(64), nullable=False)

    target_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    warning_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    critical_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_calculated")

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_risk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True)

    last_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
