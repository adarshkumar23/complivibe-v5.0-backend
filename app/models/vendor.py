import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Vendor(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        Index("ix_vendors_org_status", "organization_id", "status"),
        Index("ix_vendors_org_risk_tier", "organization_id", "risk_tier"),
        Index("ix_vendors_org_vendor_type", "organization_id", "vendor_type"),
        Index("ix_vendors_org_data_access", "organization_id", "data_access"),
        Index("ix_vendors_org_owner", "organization_id", "owner_user_id"),
        Index("ix_vendors_org_archived", "organization_id", "archived_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor_type: Mapped[str] = mapped_column(String(64), nullable=False)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    primary_contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    primary_contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    risk_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="not_assessed")
    # Provenance for risk_tier: "manual" once a human has explicitly set it via
    # PATCH /vendors/{id}, "computed" when it was last written by an automated
    # scoring/escalation path (vendor risk-score compute, questionnaire scoring,
    # sanctions/KYB escalation). Automated compute paths must not silently
    # clobber a manually-set tier -- see VendorRiskService.create_risk_score.
    risk_tier_source: Mapped[str] = mapped_column(String(32), nullable=False, default="computed")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)

    data_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processes_personal_data: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sub_processor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nth_party_risk_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nth_party_risk_severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nth_party_risk_signal_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    nth_party_risk_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
