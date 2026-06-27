import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ProcessingActivity(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "processing_activities"
    __table_args__ = (
        CheckConstraint(
            "legal_basis IN ('consent', 'contract', 'legal_obligation', 'vital_interests', 'public_task', 'legitimate_interests')",
            name="ck_processing_activities_legal_basis",
        ),
        CheckConstraint(
            "status IN ('active', 'under_review', 'suspended', 'discontinued')",
            name="ck_processing_activities_status",
        ),
        CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('low', 'medium', 'high', 'critical')",
            name="ck_processing_activities_risk_level",
        ),
        Index("ix_processing_activities_org_status", "organization_id", "status"),
        Index("ix_processing_activities_org_legal_basis", "organization_id", "legal_basis"),
        Index("ix_processing_activities_org_requires_dpia", "organization_id", "requires_dpia"),
        Index("ix_processing_activities_org_risk_level", "organization_id", "risk_level"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    legal_basis: Mapped[str] = mapped_column(String(50), nullable=False)
    legitimate_interest_justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    special_categories: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    data_subject_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    retention_period: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retention_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    recipients: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    international_transfers: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transfer_destinations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    transfer_safeguards: Mapped[str | None] = mapped_column(String(100), nullable=True)
    controller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    controller_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dpo_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requires_dpia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_dpia_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    linked_data_asset_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    linked_subprocessor_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
