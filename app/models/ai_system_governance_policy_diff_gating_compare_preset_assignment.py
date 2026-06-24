import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyDiffGatingComparePresetAssignment(
    UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base
):
    __tablename__ = "ai_system_governance_policy_diff_gating_compare_preset_assignments"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_scope", "organization_id", "scope_type"),
        Index("ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_preset", "organization_id", "preset_id"),
        Index("ix_ai_sys_gov_policy_diff_cmp_preset_assign_org_priority", "organization_id", "priority"),
    )

    preset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_compare_presets.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    scope_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

