import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotExecution(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_executions"
    __table_args__ = (
        Index("ix_governance_autopilot_executions_org_status", "organization_id", "execution_status"),
        Index("ix_governance_autopilot_executions_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_executions_org_created", "organization_id", "created_at"),
        Index("ix_governance_autopilot_executions_org_reversed", "organization_id", "reversed_at"),
    )

    execution_intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_key: Mapped[str] = mapped_column(String(128), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    target_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    execution_status: Mapped[str] = mapped_column(String(32), nullable=False, default="executed")
    before_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    after_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    reversal_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reversed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reversal_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
