import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyDiffGatingCompareReport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_policy_diff_gating_compare_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_org_created", "organization_id", "created_at"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_org_base", "organization_id", "base_gating_report_id"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_org_compare", "organization_id", "compare_gating_report_id"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_org_sev_dir", "organization_id", "severity_direction"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_org_rr_changed", "organization_id", "review_required_changed"),
    )

    base_gating_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    compare_gating_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    base_max_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    compare_max_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    severity_direction: Mapped[str] = mapped_column(String(16), nullable=False, default="unchanged")
    review_required_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compare_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason_code_changes_count: Mapped[int] = mapped_column(nullable=False, default=0)
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
