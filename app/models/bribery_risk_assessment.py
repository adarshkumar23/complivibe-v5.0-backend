import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BriberyRiskAssessment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Anti-Bribery & Corruption (ABC) risk assessment for a vendor/third party.

    Grounded in:
      - UK Bribery Act 2010 s.7 "adequate procedures" defense (MoJ guidance,
        gov.uk) six principles: proportionate procedures, top-level
        commitment, risk assessment, due diligence, communication/training,
        monitoring and review.
      - FCPA-aligned third-party risk factors per the DOJ/SEC FCPA Resource
        Guide: jurisdiction corruption risk (Transparency International
        Corruption Perceptions Index -- lower CPI implies higher risk),
        PEP (politically exposed person) exposure, gifts/hospitality
        frequency and value, and industry risk (extractives, defense,
        construction/infrastructure, healthcare/pharma, government
        contracting rated higher risk).

    The scoring weights below are an illustrative, documented weighting
    scaffold aligned with these FCPA/UK Bribery Act risk factors -- NOT a
    regulator-prescribed formula. Weights should be periodically reviewed
    per MoJ Principle 6 (Monitoring and Review). See
    app/satellites/tprm_intelligence/bribery_risk_scoring.py for the full
    computation and explainable breakdown.
    """

    __tablename__ = "bribery_risk_assessments"
    __table_args__ = (
        CheckConstraint(
            "jurisdiction_cpi_score IS NULL OR (jurisdiction_cpi_score >= 0 AND jurisdiction_cpi_score <= 100)",
            name="ck_bribery_risk_assessments_cpi_range",
        ),
        CheckConstraint(
            "pep_exposure IN ('none', 'indirect', 'direct')",
            name="ck_bribery_risk_assessments_pep_exposure",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 1",
            name="ck_bribery_risk_assessments_risk_score_range",
        ),
        CheckConstraint(
            "risk_tier IN ('low', 'medium', 'high')",
            name="ck_bribery_risk_assessments_risk_tier",
        ),
        Index("ix_bribery_risk_assessments_org_vendor_computed", "organization_id", "vendor_id", "computed_at"),
        Index("ix_bribery_risk_assessments_org_risk", "organization_id", "risk_id"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction_cpi_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pep_exposure: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    gift_hospitality_log_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    industry_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    scoring_breakdown_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    computed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Set once a "high" finding inconsistent with the vendor's overall risk_tier has
    # actually been escalated into the risk register (see
    # BriberyRiskScoringService.escalate_inconsistent_high_risk), mirroring
    # VendorConcentrationRiskDetection.risk_id's idempotency pattern so a repeat
    # compute for the same vendor never creates a duplicate Risk record.
    risk_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="SET NULL"), nullable=True)
