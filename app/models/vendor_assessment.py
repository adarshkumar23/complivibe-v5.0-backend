import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorAssessment(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_assessments"
    __table_args__ = (
        Index("ix_vendor_assessments_org_vendor", "organization_id", "vendor_id"),
        Index("ix_vendor_assessments_org_status", "organization_id", "status"),
        Index("ix_vendor_assessments_org_type", "organization_id", "assessment_type"),
        Index("ix_vendor_assessments_org_assignee", "organization_id", "assigned_to_user_id"),
        Index("ix_vendor_assessments_org_due", "organization_id", "due_date"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    assessment_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    findings_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    overall_rating: Mapped[str] = mapped_column(String(32), nullable=False, default="not_rated")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
