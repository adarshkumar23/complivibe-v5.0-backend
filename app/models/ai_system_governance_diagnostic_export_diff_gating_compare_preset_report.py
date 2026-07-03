import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetReport(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OrganizationOwnedMixin,
    Base,
):
    __tablename__ = "ai_system_gov_diag_export_diff_gating_cmp_pst_rpts_97fb99df"
    __table_args__ = (
        Index("ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_a53f6679", "organization_id", "status"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_b246ded0", "organization_id", "created_at"),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_dc134d31",
            "organization_id",
            "compare_report_id",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_d64984da",
            "organization_id",
            "preset_id",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_preset_rep_org_band",
            "organization_id",
            "interpretation_band",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_8c01536c",
            "organization_id",
            "review_required",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_rep_org_08580bd2",
            "organization_id",
            "preset_version_id",
        ),
    )

    compare_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_rpts_884d7a31.id", ondelete="CASCADE"),
        nullable=False,
    )
    preset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a.id", ondelete="CASCADE"),
        nullable=False,
    )
    preset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c.id", ondelete="SET NULL"),
        nullable=True,
    )
    preset_version_number: Mapped[int | None] = mapped_column(nullable=True)
    preset_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    version_resolution_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pinned_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c.id", ondelete="SET NULL"),
        nullable=True,
    )
    explicit_version_override_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version_override_reason: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    interpretation_band: Mapped[str] = mapped_column(String(32), nullable=False)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matched_rules_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
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
