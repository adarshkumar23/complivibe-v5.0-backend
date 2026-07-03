import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignment(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OrganizationOwnedMixin,
    Base,
):
    __tablename__ = "ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb"
    __table_args__ = (
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_65278498",
            "organization_id",
            "status",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_6af4dddb",
            "organization_id",
            "scope_type",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_93fa4c13",
            "organization_id",
            "preset_id",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_baf4b87e",
            "organization_id",
            "priority",
        ),
    )

    preset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a.id", ondelete="CASCADE"),
        nullable=False,
    )
    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
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
