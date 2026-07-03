from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ComplianceRiskRecommendation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_risk_recommendations"
    __table_args__ = (
        CheckConstraint(
            "recommendation_type IN ('gap_identified', 'treatment_change', 'new_risk', 'risk_retirement')",
            name="ck_comp_risk_rec_type",
        ),
        CheckConstraint("provider_used IN ('groq', 'azure')", name="ck_comp_risk_rec_provider"),
        CheckConstraint("status IN ('pending', 'accepted', 'dismissed', 'snoozed')", name="ck_comp_risk_rec_status"),
        CheckConstraint(
            "suggested_likelihood IS NULL OR (suggested_likelihood >= 1 AND suggested_likelihood <= 5)",
            name="ck_comp_risk_rec_lh",
        ),
        CheckConstraint(
            "suggested_impact IS NULL OR (suggested_impact >= 1 AND suggested_impact <= 5)",
            name="ck_comp_risk_rec_imp",
        ),
        Index("ix_comp_risk_rec_org_status", "organization_id", "status"),
        Index("ix_comp_risk_rec_org_type", "organization_id", "recommendation_type"),
        Index("ix_comp_risk_rec_org_bu", "organization_id", "business_unit_id"),
        Index("ix_comp_risk_rec_link", "linked_risk_id"),
    )

    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommendation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suggested_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_treatment: Mapped[str | None] = mapped_column(String(100), nullable=True)
    linked_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    context_snapshot_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    provider_used: Mapped[str] = mapped_column(String(20), nullable=False)
    used_byo_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    accepted_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    dismissed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
