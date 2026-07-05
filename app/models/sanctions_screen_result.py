import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SanctionsScreenResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sanctions_screen_results"
    __table_args__ = (
        Index("ix_sanctions_screen_results_org_vendor", "organization_id", "vendor_id"),
        Index("ix_sanctions_screen_results_org_screened", "organization_id", "screened_at"),
        Index("ix_sanctions_screen_results_org_entity", "organization_id", "entity_type", "entity_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    list_name: Mapped[str] = mapped_column(String(255), nullable=False)
    screened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    match_found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    match_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cleared_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
