import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IPAsset(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ip_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('patent', 'trademark', 'model_license', 'dataset_license')",
            name="ck_ip_assets_asset_type",
        ),
        CheckConstraint(
            "status IN ('active', 'expired', 'terminated', 'pending_renewal')",
            name="ck_ip_assets_status",
        ),
        Index("ix_ip_assets_org_asset_type", "organization_id", "asset_type"),
        Index("ix_ip_assets_org_expiry_date", "organization_id", "expiry_date"),
        Index("ix_ip_assets_org_linked_ai_system", "organization_id", "linked_ai_system_id"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    licensor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    licensee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    linked_ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
