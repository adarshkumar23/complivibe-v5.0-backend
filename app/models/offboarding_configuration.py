import uuid

from sqlalchemy import Boolean, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OffboardingConfiguration(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "offboarding_configurations"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_offboarding_configurations_organization_id"),
    )

    default_successor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    require_successor_on_deactivate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
