import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationGovernanceSetting(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "organization_governance_settings"
    __table_args__ = (
        Index(
            "ix_organization_governance_settings_org",
            "organization_id",
            unique=True,
        ),
    )

    batch_cancellation_requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    batch_cancellation_policy_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
