import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorQuestionnaireResponse(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_questionnaire_responses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'sent', 'in_progress', 'submitted', 'under_review', 'completed', 'expired')",
            name="ck_vendor_questionnaire_responses_status",
        ),
        Index("ix_vendor_questionnaire_responses_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_questionnaire_responses_org_status", "organization_id", "status"),
        Index("ix_vendor_questionnaire_responses_template_id", "template_id"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    calculated_risk_score: Mapped[int | None] = mapped_column(nullable=True)
    score_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
