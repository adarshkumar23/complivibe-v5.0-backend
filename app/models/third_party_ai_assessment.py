import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ThirdPartyAIAssessment(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "third_party_ai_assessments"
    __table_args__ = (
        CheckConstraint(
            "data_egress_type IN ('none', 'anonymized', 'identified')",
            name="ck_third_party_ai_assessments_data_egress_type",
        ),
        CheckConstraint(
            "explainability_level IS NULL OR explainability_level IN ('full', 'partial', 'none', 'not_required')",
            name="ck_third_party_ai_assessments_explainability_level",
        ),
        CheckConstraint(
            "eu_act_compliance_status IS NULL OR eu_act_compliance_status IN ('compliant', 'non_compliant', 'unknown', 'not_applicable')",
            name="ck_third_party_ai_assessments_eu_act_compliance_status",
        ),
        CheckConstraint(
            "overall_risk_level IS NULL OR overall_risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_third_party_ai_assessments_overall_risk_level",
        ),
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'archived')",
            name="ck_third_party_ai_assessments_status",
        ),
        Index("ix_third_party_ai_assessments_org_vendor", "organization_id", "vendor_id"),
        Index("ix_third_party_ai_assessments_org_status", "organization_id", "status"),
        Index("ix_third_party_ai_assessments_org_risk", "organization_id", "overall_risk_level"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    data_egress_type: Mapped[str] = mapped_column(String(20), nullable=False)
    model_card_provided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bias_testing_documented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    explainability_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contractual_ai_terms_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eu_act_compliance_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    overall_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    assessed_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
