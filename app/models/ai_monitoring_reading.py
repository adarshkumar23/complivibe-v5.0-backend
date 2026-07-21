import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid
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
        CheckConstraint(
            "collection_mode IN ('a', 'b', 'c')",
            name="ck_ai_monitoring_readings_collection_mode",
        ),
        Index("ix_ai_monitoring_readings_config_created", "config_id", "created_at"),
        Index("ix_ai_monitoring_readings_org_within", "organization_id", "within_threshold"),
        Index("ix_ai_monitoring_readings_mode_reported", "organization_id", "collection_mode", "reported_at"),
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

    # --- patent P4 collection provenance (migration 0321) -------------------------
    # How the measurement reached core: 'a' in-environment agent, 'b' external push,
    # 'c' scheduled pull. NOT NULL -- every reading arrived somehow, and 'unknown' is
    # not a useful state. Rows predating this default to 'b', the only ingest path
    # that existed before.
    collection_mode: Mapped[str] = mapped_column(String(1), nullable=False, default="b")
    # What was measured, for readings not tied to a single config.
    metric_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # How many observations the value summarises.
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Which implementation produced it, e.g. 'evidently' vs 'builtin-psi'.
    computed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # When the measurement happened, as distinct from when core received it. NULLABLE
    # and left NULL for historical rows: copying created_at here would fabricate audit
    # data by asserting the measurement happened exactly when core stored it.
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
