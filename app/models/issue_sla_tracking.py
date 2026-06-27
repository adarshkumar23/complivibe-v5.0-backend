import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IssueSLATracking(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issue_sla_tracking"
    __table_args__ = (
        Index("ix_issue_sla_tracking_issue_id", "issue_id"),
        Index("ix_issue_sla_tracking_org_response_breached", "organization_id", "response_breached"),
        Index("ix_issue_sla_tracking_org_resolution_breached", "organization_id", "resolution_breached"),
        Index("ix_issue_sla_tracking_response_deadline", "response_deadline", "response_breached"),
        Index("ix_issue_sla_tracking_resolution_deadline", "resolution_deadline", "resolution_breached"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, unique=True)
    response_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolution_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response_met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_met_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
