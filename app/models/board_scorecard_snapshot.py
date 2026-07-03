import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class BoardScorecardSnapshot(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "board_scorecard_snapshots"
    __table_args__ = (
        Index("ix_bsc_snap_org_created", "organization_id", "created_at"),
        Index("ix_bsc_snap_org_bu", "organization_id", "business_unit_id"),
    )

    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_by: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    snapshot_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    overall_compliance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    snapshot_data: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
