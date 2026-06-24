import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotNoopRunnerEvent(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_noop_runner_events"
    __table_args__ = (
        Index("ix_governance_autopilot_noop_runner_events_org_status", "organization_id", "event_status"),
        Index("ix_governance_autopilot_noop_runner_events_org_type", "organization_id", "event_type"),
        Index("ix_governance_autopilot_noop_runner_events_org_handshake", "organization_id", "runner_handshake_id"),
        Index("ix_governance_autopilot_noop_runner_events_org_session", "organization_id", "runner_session_id"),
        Index("ix_governance_autopilot_noop_runner_events_org_admission", "organization_id", "runner_admission_id"),
        Index("ix_governance_autopilot_noop_runner_events_org_simulation", "organization_id", "runner_simulation_id"),
        Index("ix_governance_autopilot_noop_runner_events_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_noop_runner_events_org_idempotency", "organization_id", "idempotency_key"),
        Index("ix_governance_autopilot_noop_runner_events_org_created", "organization_id", "created_at"),
    )

    runner_handshake_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_runner_handshakes.id", ondelete="CASCADE"),
        nullable=False,
    )
    runner_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_runner_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    runner_admission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_runner_admissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    runner_simulation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_runner_simulations.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_intents.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_status: Mapped[str] = mapped_column(String(24), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    noop_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    execution_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    event_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    noop_result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
