import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SecurityScanJob(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "security_scan_jobs"
    __table_args__ = (
        CheckConstraint(
            "scan_source IN ('trivy', 'prowler', 'openscap', 'wazuh', 'custom')",
            name="ck_security_scan_jobs_scan_source",
        ),
        CheckConstraint(
            "scan_type IN ('container_image', 'infrastructure', 'compliance', 'siem_alert', 'custom')",
            name="ck_security_scan_jobs_scan_type",
        ),
        CheckConstraint(
            "status IN ('received', 'processing', 'completed', 'failed')",
            name="ck_security_scan_jobs_status",
        ),
        Index("ix_security_scan_jobs_org_source", "organization_id", "scan_source"),
        Index("ix_security_scan_jobs_org_status", "organization_id", "status"),
        Index("ix_security_scan_jobs_submitted_at", "submitted_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scan_source: Mapped[str] = mapped_column(String(30), nullable=False)
    scan_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="received")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_findings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    critical_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    control_tests_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_metadata: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
