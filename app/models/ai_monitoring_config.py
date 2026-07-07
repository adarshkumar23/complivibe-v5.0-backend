import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIMonitoringConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_monitoring_configs"
    __table_args__ = (
        CheckConstraint(
            "metric_type IN ('accuracy', 'bias_parity_gap', 'output_drift', 'confidence_distribution', 'response_time', 'error_rate')",
            name="ck_ai_monitoring_configs_metric_type",
        ),
        CheckConstraint(
            "comparison_direction IN ('above', 'below')",
            name="ck_ai_monitoring_configs_comparison_direction",
        ),
        CheckConstraint(
            "check_frequency IS NULL OR check_frequency IN ('realtime', 'hourly', 'daily', 'weekly')",
            name="ck_ai_monitoring_configs_check_frequency",
        ),
        Index("ix_ai_monitoring_configs_org_system_active", "organization_id", "ai_system_id", "is_active"),
        Index("ix_ai_monitoring_configs_org_metric", "organization_id", "metric_type"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    comparison_direction: Mapped[str] = mapped_column(String(10), nullable=False)
    alert_on_breach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    check_frequency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    baseline_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    # Snapshot of AISystem.model_version at the time the baseline was recorded.
    # Used to flag a stale/pre-model-change baseline in the monitoring dashboard.
    baseline_model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reading_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
