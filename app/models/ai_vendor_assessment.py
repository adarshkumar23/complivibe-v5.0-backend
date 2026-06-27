import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AIVendorAssessment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_vendor_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'completed', 'archived')",
            name="ck_ai_vendor_assessments_status",
        ),
        CheckConstraint(
            "model_type IN ('llm', 'ml_classifier', 'computer_vision', 'nlp', 'recommendation', 'generative', 'other') OR model_type IS NULL",
            name="ck_ai_vendor_assessments_model_type",
        ),
        CheckConstraint(
            "overall_risk_level IN ('low', 'medium', 'high', 'critical') OR overall_risk_level IS NULL",
            name="ck_ai_vendor_assessments_overall_risk_level",
        ),
        Index("ix_ai_vendor_assessments_org_vendor", "organization_id", "vendor_id"),
        Index("ix_ai_vendor_assessments_org_status", "organization_id", "status"),
        Index("ix_ai_vendor_assessments_org_risk_level", "organization_id", "overall_risk_level"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    assessor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")

    ai_model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_model_provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    training_data_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_data_governance: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_exits_environment: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    data_exits_details: Mapped[str | None] = mapped_column(Text, nullable=True)

    bias_testing_performed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bias_testing_method: Mapped[str | None] = mapped_column(Text, nullable=True)
    bias_testing_frequency: Mapped[str | None] = mapped_column(String(100), nullable=True)
    explainability_approach: Mapped[str | None] = mapped_column(Text, nullable=True)

    human_oversight_required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    human_oversight_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_used_for_decisions: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decision_types: Mapped[str | None] = mapped_column(Text, nullable=True)

    regulatory_obligations: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    vendor_ai_policy_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    incident_history: Mapped[str | None] = mapped_column(Text, nullable=True)

    overall_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_score: Mapped[int | None] = mapped_column(nullable=True)
    assessor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
