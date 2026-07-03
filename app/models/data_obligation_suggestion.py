import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataObligationSuggestion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_obligation_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'applied', 'dismissed')",
            name="ck_data_obligation_suggestions_status",
        ),
        UniqueConstraint(
            "data_asset_id",
            "obligation_id",
            name="uq_data_obligation_suggestions_asset_obligation",
        ),
        Index("ix_data_obligation_suggestions_org_status", "organization_id", "status"),
        Index("ix_data_obligation_suggestions_org_asset", "organization_id", "data_asset_id"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    link_reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    applied_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    dismissed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
