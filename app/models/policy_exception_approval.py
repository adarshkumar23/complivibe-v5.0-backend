import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, Uuid, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class PolicyExceptionApproval(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_exception_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_policy_exception_approvals_decision",
        ),
        CheckConstraint(
            "(decision = 'approved' AND approved_expiry_date IS NOT NULL) OR (decision = 'rejected' AND approved_expiry_date IS NULL)",
            name="ck_policy_exception_approvals_decision_expiry_consistency",
        ),
        UniqueConstraint("exception_id", name="uq_policy_exception_approvals_exception_id"),
    )

    exception_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("policy_exceptions.id", ondelete="CASCADE"), nullable=False)
    reviewed_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
