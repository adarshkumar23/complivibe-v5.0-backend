import uuid

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotExecutionApprovalVote(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_execution_approval_votes"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "approval_id",
            "voter_user_id",
            name="uq_governance_autopilot_execution_approval_votes_org_approval_voter",
        ),
        Index("ix_governance_autopilot_execution_approval_votes_org_approval", "organization_id", "approval_id"),
        Index("ix_governance_autopilot_execution_approval_votes_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_execution_approval_votes_org_status", "organization_id", "vote_status"),
        Index("ix_governance_autopilot_execution_approval_votes_org_voter", "organization_id", "voter_user_id"),
    )

    approval_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_approvals.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    vote_status: Mapped[str] = mapped_column(String(32), nullable=False)
    voter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    vote_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    vote_note: Mapped[str | None] = mapped_column(Text, nullable=True)
