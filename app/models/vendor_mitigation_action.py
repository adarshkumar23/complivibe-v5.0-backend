import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class VendorMitigationAction(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "vendor_mitigation_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('policy_update', 'technical_control', 'training', 'documentation', 'audit', 'contract_amendment', 'custom')",
            name="ck_vendor_mitigation_actions_action_type",
        ),
        CheckConstraint(
            "status IN ('open', 'in_progress', 'evidence_submitted', 'accepted', 'rejected', 'overdue')",
            name="ck_vendor_mitigation_actions_status",
        ),
        Index("ix_vendor_mitigation_actions_case_id", "case_id"),
        Index("ix_vendor_mitigation_actions_org_status", "organization_id", "status"),
        Index("ix_vendor_mitigation_actions_due_status", "due_date", "status"),
    )

    case_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendor_mitigation_cases.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_to_vendor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="open")

    evidence_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True)
    evidence_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
