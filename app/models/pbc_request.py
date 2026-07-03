import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PBCRequest(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "pbc_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'submitted', 'accepted', 'rejected', 'overdue')",
            name="ck_pbc_requests_status",
        ),
        Index("ix_pbc_requests_org_audit", "organization_id", "audit_id"),
        Index("ix_pbc_requests_org_status", "organization_id", "status"),
        Index("ix_pbc_requests_org_due", "organization_id", "due_date"),
        Index("ix_pbc_requests_assigned_to", "assigned_to"),
    )

    audit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="SET NULL"), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
