import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GeopoliticalRiskSignal(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A single geopolitical risk signal detected for a region.

    Rows are normally created by ``GeopoliticalRiskService.ingest_from_gdelt``
    from real GDELT DOC API articles. ``source_error`` is NOT used to store a
    degraded/failed row in this table -- see the service module docstring for
    why a full source-fetch failure never creates a row here at all. The
    column exists for the narrower case where a source connection succeeded
    but a specific article/record could not be fully parsed (e.g. missing a
    field we expect); in that case we still persist the row (it is real data)
    with ``source_error`` describing what could not be parsed, rather than
    silently dropping it.
    """

    __tablename__ = "geopolitical_risk_signals"
    __table_args__ = (
        CheckConstraint(
            "category IN ('conflict', 'sanctions', 'political_instability', 'trade_restriction', "
            "'regulatory_change', 'other')",
            name="ck_geopolitical_risk_signals_category",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_geopolitical_risk_signals_severity",
        ),
        Index("ix_geopolitical_risk_signals_org_region", "organization_id", "region"),
        Index("ix_geopolitical_risk_signals_org_category", "organization_id", "category"),
        Index("ix_geopolitical_risk_signals_org_severity", "organization_id", "severity"),
        Index("ix_geopolitical_risk_signals_org_detected_at", "organization_id", "detected_at"),
    )

    region: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    headline: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    source_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
