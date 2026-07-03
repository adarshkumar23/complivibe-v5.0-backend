import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PolicyAttestationCampaign(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_attestation_campaigns"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_policy_attestation_campaigns_status",
        ),
        Index("ix_policy_attestation_campaigns_org_policy", "organization_id", "policy_id"),
        Index("ix_policy_attestation_campaigns_org_status", "organization_id", "status"),
        Index("ix_pat_camp_org_due", "organization_id", "due_date"),
        Index(
            "uq_policy_attestation_campaigns_org_name_active",
            "organization_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("compliance_policy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    policy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    attestation_text_shown: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    attestation_expiry_days: Mapped[int] = mapped_column(Integer, nullable=False, default=365)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
