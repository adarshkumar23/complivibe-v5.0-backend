import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyDiffGatingComparePreset(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_policy_diff_gating_compare_presets"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_created", "organization_id", "created_at"),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_baseline_report",
            "organization_id",
            "baseline_gating_report_id",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_baseline_profile",
            "organization_id",
            "baseline_gating_profile_id",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_band",
            "organization_id",
            "default_interpretation_band",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_active_ver",
            "organization_id",
            "active_version_id",
        ),
        Index(
            "ix_ai_sys_gov_policy_diff_gating_cmp_preset_org_pinned_ver",
            "organization_id",
            "pinned_version_id",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    baseline_gating_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    baseline_gating_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_policy_diff_gating_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )
    watched_reason_codes_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    ignored_reason_codes_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    interpretation_rules_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    default_interpretation_band: Mapped[str] = mapped_column(String(32), nullable=False, default="stable")
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_system_governance_policy_diff_gating_compare_preset_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_sys_gov_policy_diff_gating_cmp_presets_active_version_id",
        ),
        nullable=True,
    )
    pinned_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "ai_system_governance_policy_diff_gating_compare_preset_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_ai_sys_gov_policy_diff_gating_cmp_presets_pinned_version_id",
        ),
        nullable=True,
    )
    version_selection_mode: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active_then_mutable",
    )
    allow_explicit_version_override: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
    )
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pinned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    pin_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    unpinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unpinned_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    unpin_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
