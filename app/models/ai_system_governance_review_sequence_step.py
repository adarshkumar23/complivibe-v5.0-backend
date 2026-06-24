import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceReviewSequenceStep(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_review_sequence_steps"
    __table_args__ = (
        Index("ix_ai_sys_gov_seq_steps_org_pack", "organization_id", "sequence_pack_id"),
        Index("ix_ai_sys_gov_seq_steps_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_seq_steps_org_step_order", "organization_id", "sequence_pack_id", "step_order"),
    )

    sequence_pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_review_sequence_packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title_template: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    offset_days_from_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    default_reminder_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_review_reminder_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_assigned_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_checklist_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    require_previous_step_planned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
