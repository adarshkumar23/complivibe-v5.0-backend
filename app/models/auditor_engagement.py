import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AuditorEngagement(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "auditor_engagements"
    __table_args__ = (
        Index("ix_auditor_engagements_org_status", "organization_id", "status"),
        Index("ix_auditor_engagements_org_auditor", "organization_id", "auditor_id"),
        Index("ix_auditor_engagements_org_started", "organization_id", "started_at"),
    )

    auditor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("auditors.id", ondelete="RESTRICT"), nullable=False)
    audit_engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    framework: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revenue_share_fee_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
