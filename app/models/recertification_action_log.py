import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class RecertificationActionLog(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "recertification_action_logs"
    __table_args__ = (
        UniqueConstraint("organization_id", "idempotency_key", name="uq_recert_action_idempotency"),
        Index("ix_recert_action_org_run", "organization_id", "run_id"),
        Index("ix_recert_action_org_status", "organization_id", "action_status"),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("recertification_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("evidence_recertification_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_email_outbox_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    skipped_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
