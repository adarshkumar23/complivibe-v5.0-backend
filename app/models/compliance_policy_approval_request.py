import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class CompliancePolicyApprovalRequest(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_policy_approval_requests"
    __table_args__ = (
        Index("ix_compliance_policy_approval_requests_org_policy", "organization_id", "policy_id"),
        Index("ix_compliance_policy_approval_requests_org_version", "organization_id", "version_id"),
        Index("ix_compliance_policy_approval_requests_org_status", "organization_id", "status"),
        Index("ix_compliance_policy_approval_requests_org_created", "organization_id", "created_at"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("compliance_policy_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    approver_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
