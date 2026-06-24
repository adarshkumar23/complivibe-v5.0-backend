import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AutomationActionLog(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "automation_action_logs"
    __table_args__ = (
        Index("ix_automation_action_org_rule", "organization_id", "rule_id"),
        Index("ix_automation_action_org_execution", "organization_id", "execution_id"),
        Index("ix_automation_action_org_idempotency", "organization_id", "idempotency_key"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("automation_rule_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_task_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_email_outbox_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    skipped_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
