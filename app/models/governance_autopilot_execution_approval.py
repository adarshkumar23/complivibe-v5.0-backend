import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotExecutionApproval(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_execution_approvals"
    __table_args__ = (
        Index("ix_governance_autopilot_execution_approvals_org_status", "organization_id", "approval_status"),
        Index("ix_governance_autopilot_execution_approvals_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_execution_approvals_org_requested", "organization_id", "requested_at"),
    )

    execution_intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="requested")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_policy_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    approval_requirements_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    readiness_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
