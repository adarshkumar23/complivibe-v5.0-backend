import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DSRSLATracking(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "dsr_sla_tracking"
    __table_args__ = (
        UniqueConstraint("request_id", name="uq_dsr_sla_tracking_request"),
        Index("ix_dsr_sla_tracking_org_deadline", "organization_id", "effective_deadline"),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_subject_requests.id", ondelete="CASCADE"), nullable=False)
    effective_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    breach_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
