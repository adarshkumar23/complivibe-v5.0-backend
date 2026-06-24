import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyDiffGatingComparePresetAssignmentHistory(
    UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base
):
    __tablename__ = "ai_system_governance_policy_diff_gating_compare_preset_assignment_history"
    __table_args__ = (
        Index(
            "ix_ai_sys_gov_policy_diff_cmp_preset_assign_hist_org_assign",
            "organization_id",
            "assignment_id",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_cmp_preset_assign_hist_org_created",
            "organization_id",
            "created_at",
        ),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_compare_preset_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    before_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

