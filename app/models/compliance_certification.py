import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceCertification(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_certifications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'inactive', 'draft')",
            name="ck_compliance_certifications_status",
        ),
        Index("ix_compliance_certifications_org_status", "organization_id", "status"),
        Index("ix_compliance_certifications_org_name", "organization_id", "name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    certification_type: Mapped[str] = mapped_column(String(100), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    issued_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
