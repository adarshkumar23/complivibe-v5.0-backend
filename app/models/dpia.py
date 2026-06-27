import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DPIA(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "dpias"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'under_review', 'approved', 'rejected', 'archived')",
            name="ck_dpias_status",
        ),
        CheckConstraint(
            "residual_risk_level IS NULL OR residual_risk_level IN ('low', 'medium', 'high', 'unacceptable')",
            name="ck_dpias_residual_risk_level",
        ),
        Index("ix_dpias_org_status", "organization_id", "status"),
        Index("ix_dpias_org_activity", "organization_id", "processing_activity_id"),
        Index("ix_dpias_org_residual_risk", "organization_id", "residual_risk_level"),
    )

    processing_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_activities.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    nature_of_processing: Mapped[str | None] = mapped_column(Text, nullable=True)
    necessity_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    proportionality_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks_identified: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    risk_assessment_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mitigation_measures: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    residual_risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dpo_consulted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dpo_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    supervisory_authority_consulted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sa_consultation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
