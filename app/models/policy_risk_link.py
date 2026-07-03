import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class PolicyRiskLink(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_risk_links"
    __table_args__ = (
        UniqueConstraint("policy_id", "risk_id", name="uq_policy_risk_links_policy_risk"),
        Index("ix_policy_risk_links_org_policy", "organization_id", "policy_id"),
        Index("ix_policy_risk_links_org_risk", "organization_id", "risk_id"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    risk_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False)
    link_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlinked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    unlink_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
