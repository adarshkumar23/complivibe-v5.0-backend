import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIApprovalEnvelope(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_approval_envelopes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired')",
            name="ck_ai_approval_envelopes_status",
        ),
        Index("ix_ai_approval_envelopes_org_system", "organization_id", "ai_system_id"),
        Index("ix_ai_approval_envelopes_org_status", "organization_id", "status"),
        Index("ix_ai_approval_envelopes_expires_status", "expires_at", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    transition_from: Mapped[str] = mapped_column(String(50), nullable=False)
    transition_to: Mapped[str] = mapped_column(String(50), nullable=False)
    required_approvers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    approvals_received: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    conditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
