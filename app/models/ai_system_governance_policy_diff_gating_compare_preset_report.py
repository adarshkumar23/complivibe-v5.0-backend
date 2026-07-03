import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyDiffGatingComparePresetReport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_policy_diff_gating_compare_preset_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_created", "organization_id", "created_at"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_preset", "organization_id", "preset_id"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_base", "organization_id", "base_gating_report_id"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_compare", "organization_id", "compare_gating_report_id"),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_band",
            "organization_id",
            "interpretation_band",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_review_req",
            "organization_id",
            "review_required",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_rep_org_version",
            "organization_id",
            "preset_version_id",
        ),
    )

    preset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_compare_presets.id", ondelete="CASCADE"),
        nullable=False,
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
    compare_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_compare_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    preset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_pol_diff_gating_cmp_pst_vers_d4acbc3b.id", ondelete="SET NULL"),
        nullable=True,
    )
    preset_version_number: Mapped[int | None] = mapped_column(nullable=True)
    preset_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    interpretation_band: Mapped[str] = mapped_column(String(32), nullable=False)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    watched_reason_codes_hit_count: Mapped[int] = mapped_column(nullable=False, default=0)
    ignored_reason_codes_hit_count: Mapped[int] = mapped_column(nullable=False, default=0)
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
