import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataResidencyViolation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_residency_violations"
    __table_args__ = (
        CheckConstraint(
            "violation_type IN ('data_in_prohibited_country', 'data_outside_required_country', 'data_outside_eea', 'data_outside_domestic')",
            name="ck_data_residency_violations_violation_type",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'resolved', 'waived')",
            name="ck_data_residency_violations_status",
        ),
        Index("ix_data_residency_violations_org_asset", "organization_id", "data_asset_id"),
        Index("ix_data_residency_violations_org_status", "organization_id", "status"),
        Index("ix_data_residency_violations_detected_at", "detected_at"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_residency_policies.id", ondelete="CASCADE"), nullable=False)
    violation_type: Mapped[str] = mapped_column(String(30), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    violating_locations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_incident_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
