import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceDiagnosticExportDiffGatingReport(
    UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base
):
    __tablename__ = "ai_system_governance_diagnostic_export_diff_gating_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_diag_export_diff_gating_reports_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_reports_org_created", "organization_id", "created_at"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_reports_org_diff", "organization_id", "export_diff_report_id"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_reports_org_profile", "organization_id", "gating_profile_id"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_reports_org_review_req", "organization_id", "review_required"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_reports_org_max_severity", "organization_id", "max_severity"),
    )

    export_diff_report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_pst_assign_diag_export_diff_rpts_29e68c83.id", ondelete="CASCADE"),
        nullable=False,
    )
    gating_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_diagnostic_export_diff_gating_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    max_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    review_required: Mapped[bool] = mapped_column(nullable=False, default=False)
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
