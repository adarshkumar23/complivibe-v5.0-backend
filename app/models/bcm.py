import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class BusinessProcess(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "business_processes"
    __table_args__ = (
        CheckConstraint(
            "criticality_tier IN ('tier_1_critical', 'tier_2_high', 'tier_3_standard')",
            name="ck_business_processes_criticality_tier",
        ),
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_business_processes_status",
        ),
        Index("ix_business_processes_org_criticality", "organization_id", "criticality_tier"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    criticality_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="tier_3_standard")
    recovery_time_objective_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    recovery_point_objective_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    dependencies_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class BiaAssessment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "bia_assessments"
    __table_args__ = (
        CheckConstraint(
            "financial_impact_tier IS NULL OR financial_impact_tier IN ('low', 'medium', 'high', 'severe')",
            name="ck_bia_assessments_financial_impact_tier",
        ),
        Index("ix_bia_assessments_org_process", "organization_id", "process_id"),
    )

    process_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("business_processes.id", ondelete="CASCADE"), nullable=False
    )
    impact_analysis_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    financial_impact_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    review_frequency_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    last_reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
