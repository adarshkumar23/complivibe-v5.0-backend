import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotRunnerSimulation(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_runner_simulations"
    __table_args__ = (
        Index("ix_governance_autopilot_runner_simulations_org_status", "organization_id", "simulation_status"),
        Index("ix_governance_autopilot_runner_simulations_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_runner_simulations_org_approval", "organization_id", "approval_id"),
        Index("ix_governance_autopilot_runner_simulations_org_idempotency", "organization_id", "idempotency_key"),
        Index("ix_governance_autopilot_runner_simulations_org_created", "organization_id", "created_at"),
    )

    execution_intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_approvals.id", ondelete="SET NULL"),
        nullable=True,
    )
    simulation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    handoff_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    readiness_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    policy_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    capability_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    simulation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
