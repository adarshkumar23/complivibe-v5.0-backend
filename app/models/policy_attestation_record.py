import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PolicyAttestationRecord(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_attestation_records"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'attested', 'expired', 'exempted')",
            name="ck_policy_attestation_records_status",
        ),
        UniqueConstraint("campaign_id", "user_id", name="uq_policy_attestation_records_campaign_user"),
        Index("ix_policy_attestation_records_org_campaign", "organization_id", "campaign_id"),
        Index("ix_policy_attestation_records_org_user_status", "organization_id", "user_id", "status"),
        Index("ix_policy_attestation_records_org_status_expires", "organization_id", "status", "expires_at"),
    )

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_attestation_campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exemption_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    exempted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
