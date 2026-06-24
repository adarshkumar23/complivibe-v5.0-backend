import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePresetAssignmentDiagnosticExport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_preset_assignment_diagnostic_exports"
    __table_args__ = (
        Index("ix_ai_sys_gov_preset_assign_diag_exports_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_preset_assign_diag_exports_org_type", "organization_id", "export_type"),
        Index("ix_ai_sys_gov_preset_assign_diag_exports_org_report", "organization_id", "source_report_id"),
        Index("ix_ai_sys_gov_preset_assign_diag_exports_org_diff", "organization_id", "source_diff_report_id"),
        Index("ix_ai_sys_gov_preset_assign_diag_exports_org_created", "organization_id", "created_at"),
    )

    export_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_preset_assignment_diagnostic_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_diff_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_preset_assignment_diagnostic_diff_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    export_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    canonical_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(64), nullable=False, default="HMAC-SHA256")
    internal_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    signing_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
