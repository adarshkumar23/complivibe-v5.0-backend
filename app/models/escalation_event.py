import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EscalationEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "escalation_events"
    __table_args__ = (
        Index("ix_escalation_events_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_escalation_events_policy_entity_escalated", "policy_id", "entity_id", "escalated_at"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("escalation_policies.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    escalated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    escalated_to: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notification_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notification_queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
