import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceOperatorAcknowledgement(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_operator_acknowledgements"
    __table_args__ = (
        Index("ix_ai_sys_gov_op_ack_org_action", "organization_id", "action_type"),
        Index("ix_ai_sys_gov_op_ack_org_target", "organization_id", "target_type", "target_id"),
        Index("ix_ai_sys_gov_op_ack_org_created", "organization_id", "created_at"),
    )

    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    acknowledgement_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_freeze: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    freeze_window_ids_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
