import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePresetAssignmentDiagnosticReport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_preset_assignment_diagnostic_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_preset_assign_diag_reports_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_preset_assign_diag_reports_org_created", "organization_id", "created_at"),
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    input_contexts_json: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    context_count: Mapped[int] = mapped_column(nullable=False, default=0)
    resolved_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    unresolved_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    warning_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    critical_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    aggregate_diagnostics_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
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
