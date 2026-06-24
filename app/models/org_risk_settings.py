import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrgRiskSettings(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "org_risk_settings"

    financial_weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.400"))
    brand_weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.300"))
    operational_weight: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False, default=Decimal("0.300"))
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
