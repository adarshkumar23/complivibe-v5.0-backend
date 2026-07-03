import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemRiskAssessment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_risk_assessments"
    __table_args__ = (
        Index("ix_ai_system_risk_assessments_org_ai_system", "organization_id", "ai_system_id"),
        Index("ix_ai_system_risk_assessments_org_status", "organization_id", "status"),
        Index("ix_ai_system_risk_assessments_org_risk_level", "organization_id", "risk_level"),
        Index("ix_ai_system_risk_assessments_org_type", "organization_id", "assessment_type"),
        Index("ix_ai_system_risk_assessments_org_owner", "organization_id", "owner_user_id"),
        Index("ix_ai_system_risk_assessments_org_archived", "organization_id", "archived_at"),
        Index("ix_ai_system_risk_assessments_org_scoring_profile", "organization_id", "scoring_profile_id"),
        Index("ix_ai_system_risk_assessments_org_calculated_risk_level", "organization_id", "calculated_risk_level"),
        Index("ix_ai_system_risk_assessments_org_dimension_template", "organization_id", "dimension_template_id"),
        Index(
            "ix_ai_system_risk_assessments_org_latest_classification",
            "organization_id",
            "latest_classification_id",
        ),
        Index(
            "ix_ai_system_risk_assessments_org_calc_dim_risk_level_b75817aa",
            "organization_id",
            "calculated_dimension_risk_level",
        ),
        Index(
            "ix_ai_system_risk_assessments_org_calc_resid_risk_lev_ab05b152",
            "organization_id",
            "calculated_residual_risk_level",
        ),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    likelihood: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    impact: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    inherent_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_dimensions_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    risk_factors_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    mitigation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v1")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    scoring_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_scoring_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    scoring_profile_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    score_explanation_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    calculated_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    dimension_template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_dimension_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    latest_classification_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_system_risk_classification_records.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_system_risk_assessments_latest_classification_id",
        ),
        nullable=True,
    )
    classification_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    classification_summary_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    latest_classification_review_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    open_signal_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dimension_template_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    dimension_inputs_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    dimension_score_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    dimension_weighted_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    calculated_dimension_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    residual_likelihood: Mapped[str | None] = mapped_column(String(32), nullable=True)
    residual_impact: Mapped[str | None] = mapped_column(String(32), nullable=True)
    calculated_residual_risk_level: Mapped[str | None] = mapped_column(String(32), nullable=True)
    residual_score_explanation_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
