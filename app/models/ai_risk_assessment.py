import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIRiskAssessment(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_risk_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'archived')",
            name="ck_ai_risk_assessments_status",
        ),
        CheckConstraint(
            "bias_risk_rating IS NULL OR bias_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_bias_rating",
        ),
        CheckConstraint(
            "fairness_risk_rating IS NULL OR fairness_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_fairness_rating",
        ),
        CheckConstraint(
            "explainability_risk_rating IS NULL OR explainability_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_explainability_rating",
        ),
        CheckConstraint(
            "privacy_risk_rating IS NULL OR privacy_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_privacy_rating",
        ),
        CheckConstraint(
            "misuse_risk_rating IS NULL OR misuse_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_misuse_rating",
        ),
        CheckConstraint(
            "security_risk_rating IS NULL OR security_risk_rating IN ('low', 'medium', 'high', 'critical')",
            name="ck_ai_risk_assessments_security_rating",
        ),
        Index("ix_ai_risk_assessments_org_system", "organization_id", "ai_system_id"),
        Index("ix_ai_risk_assessments_org_status", "organization_id", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    assessment_version: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    bias_risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fairness_risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    explainability_risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    privacy_risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    misuse_risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    security_risk_rating: Mapped[str | None] = mapped_column(String(20), nullable=True)
    overall_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    assessment_bias_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
