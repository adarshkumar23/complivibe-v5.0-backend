import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceBaselineRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_baseline_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','completed','failed')", name="ck_compliance_baseline_runs_status"),
        CheckConstraint(
            "integration_provider IN ('github','aws','okta') OR integration_provider IS NULL",
            name="ck_compliance_baseline_runs_provider",
        ),
        Index("ix_compliance_baseline_runs_org_status", "organization_id", "status"),
        Index("ix_compliance_baseline_runs_org_created", "organization_id", "created_at"),
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    selected_framework_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    intake_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("inbound_questionnaire_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    integration_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gap_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
