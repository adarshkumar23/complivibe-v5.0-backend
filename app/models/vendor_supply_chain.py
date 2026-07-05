import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class VendorSupplyChainLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_supply_chain_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "parent_vendor_id", "sub_vendor_id", "relationship_type", "is_active", name="uq_vendor_supply_chain_active_link"),
        Index("ix_vendor_supply_chain_parent", "organization_id", "parent_vendor_id", "is_active"),
        Index("ix_vendor_supply_chain_sub", "organization_id", "sub_vendor_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    parent_vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    sub_vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False, default="supplier")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class VendorSupplyChainAlert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "vendor_supply_chain_alerts"
    __table_args__ = (
        Index("ix_vendor_supply_chain_alerts_org_parent", "organization_id", "parent_vendor_id", "status"),
        Index("ix_vendor_supply_chain_alerts_org_trigger", "organization_id", "triggering_vendor_id", "signal_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    parent_vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    triggering_vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    source_entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
