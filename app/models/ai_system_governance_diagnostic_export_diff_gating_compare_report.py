import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceDiagnosticExportDiffGatingCompareReport(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OrganizationOwnedMixin,
    Base,
):
    __tablename__ = "ai_system_governance_diagnostic_export_diff_gating_compare_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_diag_export_diff_gating_cmp_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_cmp_org_created", "organization_id", "created_at"),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_org_base",
            "organization_id",
            "base_gating_report_id",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_org_compare",
            "organization_id",
            "compare_gating_report_id",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_org_sev_drift",
            "organization_id",
            "max_severity_drift",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_org_rr_drift",
            "organization_id",
            "review_required_drift",
        ),
    )

    base_gating_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_diagnostic_export_diff_gating_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    compare_gating_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_diagnostic_export_diff_gating_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    max_severity_drift: Mapped[str] = mapped_column(String(16), nullable=False, default="unchanged")
    review_required_drift: Mapped[str] = mapped_column(String(32), nullable=False, default="unchanged")
    reason_code_changes_count: Mapped[int] = mapped_column(nullable=False, default=0)
    severity_changes_count: Mapped[int] = mapped_column(nullable=False, default=0)
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
