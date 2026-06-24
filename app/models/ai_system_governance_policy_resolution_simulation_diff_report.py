import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyResolutionSimulationDiffReport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_policy_resolution_simulation_diff_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_res_sim_diff_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_res_sim_diff_org_created", "organization_id", "created_at"),
        Index("ix_ai_sys_gov_policy_res_sim_diff_org_base", "organization_id", "base_report_id"),
        Index("ix_ai_sys_gov_policy_res_sim_diff_org_compare", "organization_id", "compare_report_id"),
    )

    base_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_resolution_simulation_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    compare_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_resolution_simulation_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    diff_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    context_match_strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="context_key_then_index")
    added_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    removed_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    changed_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    unchanged_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    blocked_delta: Mapped[int] = mapped_column(nullable=False, default=0)
    warning_delta: Mapped[int] = mapped_column(nullable=False, default=0)
    no_policy_delta: Mapped[int] = mapped_column(nullable=False, default=0)
    reason_code_summary_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    reason_code_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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
