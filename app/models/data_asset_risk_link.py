import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataAssetRiskLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_asset_risk_links"
    __table_args__ = (
        UniqueConstraint("data_asset_id", "risk_id", name="uq_darl_asset_risk"),
        Index("ix_darl_org_asset", "organization_id", "data_asset_id"),
        Index("ix_darl_org_risk", "organization_id", "risk_id"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    risk_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
