import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Subprocessor(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "subprocessors"
    __table_args__ = (
        CheckConstraint(
            "legal_basis IN ('contract', 'legitimate_interest', 'consent', 'legal_obligation', 'vital_interests', 'public_task')",
            name="ck_subprocessors_legal_basis",
        ),
        CheckConstraint(
            "data_transfer_mechanism IN ('sccs', 'adequacy_decision', 'bcrs', 'derogation', 'not_applicable') OR data_transfer_mechanism IS NULL",
            name="ck_subprocessors_data_transfer_mechanism",
        ),
        CheckConstraint(
            "dpa_status IN ('pending', 'signed', 'not_required', 'expired', 'under_review')",
            name="ck_subprocessors_dpa_status",
        ),
        CheckConstraint(
            "controller_type IN ('processor', 'sub_processor', 'joint_controller')",
            name="ck_subprocessors_controller_type",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_subprocessors_risk_level",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'under_review', 'offboarded')",
            name="ck_subprocessors_status",
        ),
        Index("ix_subprocessors_org_status", "organization_id", "status"),
        Index("ix_subprocessors_org_dpa_status", "organization_id", "dpa_status"),
        Index("ix_subprocessors_org_risk_level", "organization_id", "risk_level"),
        Index("ix_subprocessors_dpa_expiry_status", "dpa_expiry_date", "dpa_status"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    service_description: Mapped[str] = mapped_column(Text, nullable=False)
    data_types_processed: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    legal_basis: Mapped[str] = mapped_column(String(100), nullable=False)
    geographic_locations: Mapped[list | dict] = mapped_column(JSON, nullable=False, default=list)
    data_transfer_mechanism: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dpa_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    dpa_signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dpa_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dpa_document_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    controller_type: Mapped[str] = mapped_column(String(50), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    review_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
