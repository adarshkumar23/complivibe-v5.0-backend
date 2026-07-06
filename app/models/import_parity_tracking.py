import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class ImportParityTracking(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "import_parity_tracking"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('control', 'evidence', 'policy', 'business_unit')",
            name="ck_import_parity_tracking_entity_type",
        ),
        CheckConstraint("imported_count >= 0", name="ck_import_parity_tracking_imported_count"),
        CheckConstraint("verified_count >= 0", name="ck_import_parity_tracking_verified_count"),
        CheckConstraint("parity_pct >= 0 AND parity_pct <= 100", name="ck_import_parity_tracking_parity_pct"),
        UniqueConstraint(
            "organization_id",
            "entity_type",
            "tool_source",
            name="uq_import_parity_tracking_org_entity_tool",
        ),
        Index("ix_import_parity_tracking_org_tool", "organization_id", "tool_source"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verified_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parity_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    tool_source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
