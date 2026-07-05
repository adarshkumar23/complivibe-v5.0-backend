from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IPAssetSettings(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ip_asset_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_ip_asset_settings_organization_id"),
    )

    expiring_soon_window_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
