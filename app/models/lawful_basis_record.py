import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class LawfulBasisRecord(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "lawful_basis_records"
    __table_args__ = (
        CheckConstraint(
            "lawful_basis IN ('consent', 'contract', 'legal_obligation', 'vital_interests', 'public_task', 'legitimate_interests')",
            name="ck_lawful_basis_records_lawful_basis",
        ),
        UniqueConstraint(
            "organization_id",
            "processing_activity_id",
            "lawful_basis",
            name="uq_lawful_basis_records_org_activity_basis",
        ),
        Index("ix_lawful_basis_org_basis", "organization_id", "lawful_basis"),
        Index("ix_lawful_basis_org_activity", "organization_id", "processing_activity_id"),
        Index("ix_lawful_basis_org_active", "organization_id", "is_active"),
    )

    processing_activity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("processing_activities.id", ondelete="CASCADE"), nullable=False
    )
    lawful_basis: Mapped[str] = mapped_column(String(50), nullable=False)
    basis_description: Mapped[str] = mapped_column(Text, nullable=False)
    applicable_frameworks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    article_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legitimate_interest_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_required_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    documented_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    documented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
