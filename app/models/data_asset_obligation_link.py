import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataAssetObligationLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_asset_obligation_links"
    __table_args__ = (
        CheckConstraint(
            "link_type IN ('governed_by', 'subject_to', 'exempted_from')",
            name="ck_data_asset_obligation_links_link_type",
        ),
        UniqueConstraint(
            "organization_id",
            "data_asset_id",
            "obligation_id",
            name="uq_data_asset_obligation_links_org_asset_obligation",
        ),
        Index("ix_data_asset_obligation_links_org_asset", "organization_id", "data_asset_id"),
        Index("ix_data_asset_obligation_links_org_obligation", "organization_id", "obligation_id"),
        Index("ix_data_asset_obligation_links_org_link_type", "organization_id", "link_type"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    link_type: Mapped[str] = mapped_column(String(30), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
