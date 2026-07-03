import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceDiagnosticExportDiffGatingComparePresetAssignmentHistory(
    UUIDPrimaryKeyMixin,
    TimestampMixin,
    OrganizationOwnedMixin,
    Base,
):
    __tablename__ = "ai_system_gov_diag_export_diff_gating_cmp_pst_assign_21af53f8"
    __table_args__ = (
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_8b572bad",
            "organization_id",
            "assignment_id",
        ),
        Index(
            "ix_ai_sys_gov_diag_export_diff_gating_cmp_pst_assign_068f8286",
            "organization_id",
            "event_type",
        ),
    )

    assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_gov_diag_export_diff_gating_cmp_pst_assigns_4644e2cb.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    before_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
