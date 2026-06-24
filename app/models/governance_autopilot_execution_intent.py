import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotExecutionIntent(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_execution_intents"
    __table_args__ = (
        Index("ix_governance_autopilot_execution_intents_org_status", "organization_id", "intent_status"),
        Index("ix_governance_autopilot_execution_intents_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_governance_autopilot_execution_intents_org_policy", "organization_id", "policy_id"),
        Index("ix_governance_autopilot_execution_intents_org_created", "organization_id", "created_at"),
    )

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    intent_status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    plan_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    capability_decisions_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    approval_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    blocked: Mapped[bool] = mapped_column(nullable=False, default=False)
    blocked_reasons_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_entities_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    intent_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
