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

    # NULLABLE since 0321. A metric can be collected for a system before anyone has
    # configured a threshold for it (patent-P4 Mode A/C collection); such a measurement
    # is still a fact worth keeping. Every consumer must therefore handle None.
    config_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_monitoring_configs.id", ondelete="CASCADE"), nullable=True
    )
    value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    reading_source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # NULLABLE since 0321, meaning "no single-config verdict" -- a tiered reading has one
    # verdict per tier, recorded in ai_monitoring_breach_events, and a single boolean
    # cannot represent that.
    #
    # CAUTION: None is NOT False here. `not reading.within_threshold` is True for an
    # unjudged reading and would report a breach nobody determined. Compare explicitly
    # (`is False` in Python, `.is_(False)` in SQL) at every consumer.
    within_threshold: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
