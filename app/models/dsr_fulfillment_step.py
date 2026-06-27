import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DSRFulfillmentStep(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "dsr_fulfillment_steps"
    __table_args__ = (
        CheckConstraint(
            "step_type IN ('identity_check', 'locate_data', 'review_data', 'prepare_response', 'legal_review', 'send_response', 'custom')",
            name="ck_dsr_fulfillment_steps_step_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'skipped')",
            name="ck_dsr_fulfillment_steps_status",
        ),
        Index("ix_dsr_fulfillment_steps_request_order", "request_id", "order_index"),
        Index("ix_dsr_fulfillment_steps_org_status", "organization_id", "status"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_subject_requests.id", ondelete="CASCADE"), nullable=False)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
