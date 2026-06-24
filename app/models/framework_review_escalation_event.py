import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkReviewEscalationEvent(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_review_escalation_events"
    __table_args__ = (
        Index("ix_framework_review_escalations_org_status", "organization_id", "status"),
        Index("ix_framework_review_escalations_org_event_type", "organization_id", "event_type"),
        Index("ix_framework_review_escalations_org_review", "organization_id", "review_run_id"),
        Index("ix_framework_review_escalations_org_triggered", "organization_id", "triggered_at"),
    )

    review_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_review_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
