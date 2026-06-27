import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIMonitoringReading(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_monitoring_readings"
    __table_args__ = (
        CheckConstraint(
            "reading_source IN ('manual', 'api_report')",
            name="ck_ai_monitoring_readings_reading_source",
        ),
        Index("ix_ai_monitoring_readings_config_created", "config_id", "created_at"),
        Index("ix_ai_monitoring_readings_org_within", "organization_id", "within_threshold"),
    )

    config_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_monitoring_configs.id", ondelete="CASCADE"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    reading_source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    within_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
