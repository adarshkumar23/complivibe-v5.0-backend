import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class TrustCenterPublishedPolicy(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "trust_center_published_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "policy_id", name="uq_trust_center_published_policies_org_policy"),
        Index("ix_trust_center_published_policies_org_active", "organization_id", "is_active"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    published_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
