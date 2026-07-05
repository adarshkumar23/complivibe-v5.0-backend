import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AiUsagePolicyCheck(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Bridges AI Governance (AISystem) and Policy Management (CompliancePolicy /
    PolicyAttestationCampaign / PolicyAttestationRecord) by recording, per AI
    system, whether that system's usage is currently covered by an attested
    usage policy.

    One current row is kept per ai_system_id (upserted on each run by
    AiUsagePolicyService.bulk_run_for_org / run_compliance_check) rather than
    an unbounded history table -- last_checked_at is bumped on every re-run.
    """

    __tablename__ = "ai_usage_policy_checks"
    __table_args__ = (
        CheckConstraint(
            "compliance_status IN ("
            "'compliant', 'non_compliant_no_policy', 'non_compliant_expired_attestation', "
            "'non_compliant_never_attested', 'not_applicable'"
            ")",
            name="ck_ai_usage_policy_checks_compliance_status",
        ),
        Index("ix_ai_usage_policy_checks_org_ai_system", "organization_id", "ai_system_id", unique=True),
        Index("ix_ai_usage_policy_checks_org_status", "organization_id", "compliance_status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("compliance_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    compliance_status: Mapped[str] = mapped_column(String(30), nullable=False)
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
