import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class VendorRiskScore(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_risk_scores"
    __table_args__ = (
        Index("ix_vendor_risk_scores_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_risk_scores_org_assessment", "organization_id", "assessment_id"),
        Index("ix_vendor_risk_scores_org_level", "organization_id", "risk_level"),
        Index("ix_vendor_risk_scores_org_created", "organization_id", "created_at"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    assessment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("vendor_assessments.id", ondelete="SET NULL"), nullable=True)

    likelihood: Mapped[str] = mapped_column(String(16), nullable=False)
    impact: Mapped[str] = mapped_column(String(16), nullable=False)
    inherent_risk_score: Mapped[int] = mapped_column(nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    score_explanation_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)

    scored_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
