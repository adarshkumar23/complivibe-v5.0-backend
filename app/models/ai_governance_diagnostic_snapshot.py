from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Uuid, func
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIGovernanceDiagnosticSnapshot(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_governance_diagnostic_snapshots"
    __table_args__ = (
        Index("ix_ai_gov_diag_org_created", "organization_id", "created_at"),
        Index("ix_ai_gov_diag_org_bu", "organization_id", "business_unit_id"),
        Index("ix_ai_gov_diag_org_health", "organization_id", "overall_health"),
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
    overall_governance_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    overall_health: Mapped[str] = mapped_column(String(20), nullable=False)
    snapshot_data: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    ai_systems_assessed: Mapped[int] = mapped_column(Integer, nullable=False)
    critical_gaps_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
