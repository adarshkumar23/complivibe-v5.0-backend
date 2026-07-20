import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ControlExceptionApproval(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_exception_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'skipped')",
            name="ck_control_exception_approvals_status",
        ),
        Index("ix_control_exception_approvals_exception_sequence", "exception_id", "sequence"),
        Index("ix_control_exception_approvals_org_approver_status", "organization_id", "approver_user_id", "status"),
    )

    exception_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("control_exceptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    approver_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # The identity that actually recorded the decision on this step. Distinct from
    # approver_user_id, which is the *assigned* approver: an override holder may
    # decide a step assigned to someone else. Distinct-identity (four-eyes)
    # enforcement across steps keys on this actual-decider column, not on the
    # assignment, so an override-approved step still counts against the decider.
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
