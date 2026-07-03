import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PolicyAttestation(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_attestations"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'attested', 'declined')", name="ck_pol_att_status"),
        UniqueConstraint("campaign_id", "user_id", name="uq_pol_att_campaign_user"),
        Index("ix_pol_att_org_campaign", "organization_id", "campaign_id"),
        Index("ix_pol_att_org_user", "organization_id", "user_id"),
        Index("ix_pol_att_org_status", "organization_id", "status"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_attestation_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
