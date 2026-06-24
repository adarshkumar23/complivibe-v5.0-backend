import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotRunnerSession(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_runner_sessions"
    __table_args__ = (
        Index("ix_governance_autopilot_runner_sessions_org_status", "organization_id", "session_status"),
        Index("ix_governance_autopilot_runner_sessions_org_admission", "organization_id", "runner_admission_id"),
        Index("ix_governance_autopilot_runner_sessions_org_simulation", "organization_id", "runner_simulation_id"),
        Index("ix_governance_autopilot_runner_sessions_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_runner_sessions_org_expires", "organization_id", "expires_at"),
        Index("ix_governance_autopilot_runner_sessions_org_created", "organization_id", "created_at"),
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
    session_status: Mapped[str] = mapped_column(String(32), nullable=False)
    admission_token_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_token_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lease_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    binding_context_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(nullable=False, default=3, server_default="3")
    replay_window_seconds: Mapped[int] = mapped_column(nullable=False, default=600, server_default="600")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
