import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DPIAChecklistItem(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "dpia_checklist_items"
    __table_args__ = (
        CheckConstraint("response IS NULL OR response IN ('yes', 'no', 'partial', 'na')", name="ck_dpia_checklist_items_response"),
        UniqueConstraint("dpia_id", "criterion_key", name="uq_dpia_checklist_items_dpia_criterion"),
        Index("ix_dpia_checklist_org_dpia", "organization_id", "dpia_id"),
    )

    dpia_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("dpias.id", ondelete="CASCADE"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    response: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
