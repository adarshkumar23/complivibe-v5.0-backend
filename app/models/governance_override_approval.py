import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GovernanceOverrideApproval(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_override_approvals"
    __table_args__ = (
        UniqueConstraint("override_request_id", "approver_user_id", name="uq_override_approval_once"),
        Index("ix_override_approvals_org_request", "organization_id", "override_request_id"),
    )

    override_request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_override_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    approver_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
