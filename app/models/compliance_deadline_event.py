import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ComplianceDeadlineEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_deadline_events"
    __table_args__ = (
        Index("ix_compliance_deadline_events_org_deadline", "organization_id", "deadline_id"),
        Index("ix_compliance_deadline_events_org_type", "organization_id", "event_type"),
        Index("ix_compliance_deadline_events_org_created", "organization_id", "created_at"),
    )

    deadline_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_deadlines.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outbox_queued: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
