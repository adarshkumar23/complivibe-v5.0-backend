import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkPackReviewRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_pack_review_runs"
    __table_args__ = (
        Index("ix_framework_pack_review_runs_org_framework", "organization_id", "framework_id"),
        Index("ix_framework_pack_review_runs_org_status", "organization_id", "status"),
        Index("ix_framework_pack_review_runs_org_started_at", "organization_id", "started_at"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    framework_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    pack_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    coverage_report_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_pack_coverage_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_coverage_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    checklist_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    findings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    coverage_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    caveat: Mapped[str] = mapped_column(Text, nullable=False)
