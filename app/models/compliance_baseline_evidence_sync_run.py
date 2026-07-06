import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceBaselineEvidenceSyncRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_baseline_evidence_sync_runs"
    __table_args__ = (
        CheckConstraint("provider IN ('github','aws','okta')", name="ck_compliance_baseline_sync_runs_provider"),
        CheckConstraint("status IN ('running','completed','failed')", name="ck_compliance_baseline_sync_runs_status"),
        Index("ix_compliance_baseline_sync_runs_org_provider", "organization_id", "provider"),
        Index("ix_compliance_baseline_sync_runs_baseline", "baseline_run_id"),
    )

    baseline_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("compliance_baseline_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    collected_evidence_count: Mapped[int] = mapped_column(nullable=False, default=0)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
