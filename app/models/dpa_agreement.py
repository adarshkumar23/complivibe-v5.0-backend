import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DPAAgreement(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "dpa_agreements"
    __table_args__ = (
        CheckConstraint(
            "counterparty_type IN ('processor', 'sub_processor', 'joint_controller', 'controller')",
            name="ck_dpa_agreements_counterparty_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'under_review', 'terminated')",
            name="ck_dpa_agreements_status",
        ),
        Index("ix_dpa_agreements_org_status", "organization_id", "status"),
        Index("ix_dpa_agreements_org_counterparty_type", "organization_id", "counterparty_type"),
        Index("ix_dpa_agreements_expiry_status", "expiry_date", "status"),
        Index("ix_dpa_agreements_org_vendor", "organization_id", "vendor_id"),
        Index("ix_dpa_agreements_org_subprocessor", "organization_id", "subprocessor_id"),
    )

    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    counterparty_type: Mapped[str] = mapped_column(String(20), nullable=False)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    subprocessor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    dpa_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    signed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    auto_renews: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    renewal_notice_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    governing_regulation: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    article28_compliant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sccs_included: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    bcrs_included: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    data_transfer_countries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    processing_activity_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
