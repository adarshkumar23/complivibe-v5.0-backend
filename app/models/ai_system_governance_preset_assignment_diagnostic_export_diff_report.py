import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePresetAssignmentDiagnosticExportDiffReport(
    UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base
):
    __tablename__ = "ai_system_governance_preset_assignment_diagnostic_export_diff_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_preset_assign_diag_export_diff_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_preset_assign_diag_export_diff_org_type", "organization_id", "export_type"),
        Index("ix_ai_sys_gov_preset_assign_diag_export_diff_org_base", "organization_id", "base_export_id"),
        Index("ix_ai_sys_gov_preset_assign_diag_export_diff_org_compare", "organization_id", "compare_export_id"),
        Index("ix_ai_sys_gov_preset_assign_diag_export_diff_org_created", "organization_id", "created_at"),
    )

    base_export_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_preset_assignment_diagnostic_exports.id", ondelete="CASCADE"),
        nullable=False,
    )
    compare_export_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_preset_assignment_diagnostic_exports.id", ondelete="CASCADE"),
        nullable=False,
    )
    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    diff_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    base_canonical_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    compare_canonical_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_valid_signature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compare_valid_signature: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    base_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compare_trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    added_paths_count: Mapped[int] = mapped_column(nullable=False, default=0)
    removed_paths_count: Mapped[int] = mapped_column(nullable=False, default=0)
    changed_paths_count: Mapped[int] = mapped_column(nullable=False, default=0)
    unchanged_paths_count: Mapped[int] = mapped_column(nullable=False, default=0)
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
