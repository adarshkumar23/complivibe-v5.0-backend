import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceAutopilotPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_autopilot_policies"
    __table_args__ = (
        Index("ix_governance_autopilot_policies_org_status", "organization_id", "status"),
        Index("ix_governance_autopilot_policies_org_default", "organization_id", "is_default"),
        Index("ix_governance_autopilot_policies_org_mode", "organization_id", "mode"),
        Index("ix_governance_autopilot_policies_org_created", "organization_id", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="suggest_only")

    allowed_action_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocked_action_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_draft_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocked_draft_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_signal_reason_codes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocked_signal_reason_codes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approval_required_action_types_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    approval_required_priority_bands_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    max_allowed_priority_band_for_auto: Mapped[str] = mapped_column(String(16), nullable=False, default="low")

    external_effects_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    task_creation_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    review_creation_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    source_record_mutation_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    policy_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)

    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
