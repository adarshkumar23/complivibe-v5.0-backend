import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotRunnerHandshake(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_runner_handshakes"
    __table_args__ = (
        Index("ix_governance_autopilot_runner_handshakes_org_status", "organization_id", "handshake_status"),
        Index("ix_governance_autopilot_runner_handshakes_org_session", "organization_id", "runner_session_id"),
        Index("ix_governance_autopilot_runner_handshakes_org_admission", "organization_id", "runner_admission_id"),
        Index("ix_governance_autopilot_runner_handshakes_org_simulation", "organization_id", "runner_simulation_id"),
        Index("ix_governance_autopilot_runner_handshakes_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_runner_handshakes_org_idempotency", "organization_id", "idempotency_key"),
        Index("ix_governance_autopilot_runner_handshakes_org_created", "organization_id", "created_at"),
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
    handshake_status: Mapped[str] = mapped_column(String(48), nullable=False)
    handshake_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    session_verification_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    admission_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    simulation_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    intent_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    handshake_nonce_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handshake_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    handshake_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
