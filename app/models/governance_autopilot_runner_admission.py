import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotRunnerAdmission(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_runner_admissions"
    __table_args__ = (
        Index("ix_governance_autopilot_runner_admissions_org_status", "organization_id", "admission_status"),
        Index("ix_governance_autopilot_runner_admissions_org_simulation", "organization_id", "runner_simulation_id"),
        Index("ix_governance_autopilot_runner_admissions_org_intent", "organization_id", "execution_intent_id"),
        Index("ix_governance_autopilot_runner_admissions_org_approval", "organization_id", "approval_id"),
        Index("ix_governance_autopilot_runner_admissions_org_idempotency", "organization_id", "idempotency_key"),
        Index("ix_governance_autopilot_runner_admissions_org_created", "organization_id", "created_at"),
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
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("governance_autopilot_execution_approvals.id", ondelete="SET NULL"),
        nullable=True,
    )
    admission_status: Mapped[str] = mapped_column(String(32), nullable=False)
    readiness_snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    consistency_checks_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    handoff_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    handoff_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    handoff_token_fingerprint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    admitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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
