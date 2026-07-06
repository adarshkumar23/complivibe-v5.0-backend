import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class CompetitorPricingEntry(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "competitor_pricing_entries"
    __table_args__ = (
        UniqueConstraint("version_id", "competitor_key", name="uq_competitor_pricing_entries_version_key"),
        CheckConstraint(
            "competitor_key IN ('vanta', 'drata', 'sprinto', 'scrut', 'onetrust', 'credo_ai')",
            name="ck_competitor_pricing_entries_competitor_key",
        ),
        CheckConstraint(
            "pricing_model IN ('contact_sales', 'tiered_quote', 'starting_from', 'custom_package')",
            name="ck_competitor_pricing_entries_pricing_model",
        ),
        Index("ix_competitor_pricing_entries_version_id", "version_id"),
        Index("ix_competitor_pricing_entries_competitor_key", "competitor_key"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("competitor_pricing_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    competitor_key: Mapped[str] = mapped_column(String(32), nullable=False)
    competitor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing_model: Mapped[str] = mapped_column(String(32), nullable=False)
    public_pricing_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pricing_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), nullable=False)
    source_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    starting_price_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    starting_price_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
