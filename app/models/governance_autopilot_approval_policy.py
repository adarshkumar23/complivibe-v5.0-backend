import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotApprovalPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_approval_policies"
    __table_args__ = (
        Index("ix_governance_autopilot_approval_policies_org_status", "organization_id", "status"),
        Index("ix_governance_autopilot_approval_policies_org_default", "organization_id", "is_default"),
        Index("ix_governance_autopilot_approval_policies_org_created", "organization_id", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)

    minimum_approvals: Mapped[int] = mapped_column(nullable=False, default=1)
    rejection_threshold: Mapped[int] = mapped_column(nullable=False, default=1)
    require_distinct_approvers: Mapped[bool] = mapped_column(nullable=False, default=True)
    block_requester_self_approval: Mapped[bool] = mapped_column(nullable=False, default=True)
    require_quorum_for_priority_bands_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    require_quorum_for_source_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    policy_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
