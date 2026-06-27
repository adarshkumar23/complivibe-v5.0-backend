import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIGovernanceEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_governance_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'scheduler', 'system')", name="ck_ai_governance_events_actor_type"),
        Index("ix_ai_governance_events_org_event_created", "organization_id", "event_type", "created_at"),
        Index("ix_ai_governance_events_org_system_created", "organization_id", "ai_system_id", "created_at"),
        Index("ix_ai_governance_events_created", "created_at"),
    )

    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    event_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
