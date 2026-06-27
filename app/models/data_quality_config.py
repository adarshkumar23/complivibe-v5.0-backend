import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataQualityConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_quality_configs"
    __table_args__ = (
        CheckConstraint(
            "metric_type IN ('completeness', 'accuracy', 'freshness', 'consistency', 'uniqueness')",
            name="ck_data_quality_configs_metric_type",
        ),
        CheckConstraint(
            "comparison_direction IN ('above', 'below')",
            name="ck_data_quality_configs_comparison_direction",
        ),
        CheckConstraint(
            "measurement_frequency IS NULL OR measurement_frequency IN ('realtime', 'hourly', 'daily', 'weekly')",
            name="ck_data_quality_configs_measurement_frequency",
        ),
        Index("ix_data_quality_configs_org_asset_active", "organization_id", "data_asset_id", "is_active"),
        Index("ix_data_quality_configs_org_metric", "organization_id", "metric_type"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    comparison_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    alert_on_breach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    measurement_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
