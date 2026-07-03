import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetVersion(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OrganizationOwnedMixin,
    Base,
):
    __tablename__ = "ai_system_gov_diag_export_diff_gating_cmp_pst_vers_e1cd192c"
    __table_args__ = (
        Index("ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_808bfd21", "organization_id", "preset_id"),
        Index("ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_c0d13057", "organization_id", "status"),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_ver_org_3d2e08a6",
            "organization_id",
            "preset_id",
            "version_number",
        ),
    )

    preset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_presets_ac16f85a.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
