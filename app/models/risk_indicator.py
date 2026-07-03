import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, JSON, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Native Postgres ENUM types created explicitly in migration 0092 (grandfathered
# exception to the no-native-ENUM rule). create_type=False because the migration
# owns CREATE TYPE/DROP TYPE; sa.Enum falls back to a CHECK-constrained VARCHAR
# on sqlite, so this stays cross-dialect for tests.
_metric_type_enum = Enum(
    "control_expiry_rate",
    "evidence_gap_rate",
    "overdue_task_rate",
    "vendor_high_risk_count",
    "open_alert_count",
    "policy_overdue_review",
    "custom",
    name="risk_indicator_metric_type_enum",
    create_type=False,
)
_status_enum = Enum(
    "green", "amber", "red", "not_calculated", name="risk_indicator_status_enum", create_type=False
)


class RiskIndicator(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "risk_indicators"
    __table_args__ = (
        Index("ix_risk_indicators_org_active", "organization_id", "is_active"),
        Index("ix_risk_indicators_org_metric_type", "organization_id", "metric_type"),
        Index("ix_risk_indicators_org_status", "organization_id", "status"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_type: Mapped[str] = mapped_column(_metric_type_enum, nullable=False)

    target_value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    warning_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    critical_threshold: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    status: Mapped[str] = mapped_column(_status_enum, nullable=False, default="not_calculated")

    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_risk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True)

    last_calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
