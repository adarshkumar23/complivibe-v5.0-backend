import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class AIEnvelopeApproval(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "ai_envelope_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved', 'rejected')",
            name="ck_ai_envelope_approvals_decision",
        ),
        UniqueConstraint("envelope_id", "approver_id", name="uq_ai_envelope_approvals_envelope_approver"),
    )

    envelope_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_approval_envelopes.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
