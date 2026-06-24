import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ComplianceReport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_reports"
    __table_args__ = (
        Index("ix_compliance_reports_org_type", "organization_id", "report_type"),
        Index("ix_compliance_reports_org_status", "organization_id", "status"),
        Index("ix_compliance_reports_org_generated", "organization_id", "generated_at"),
    )

    report_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    framework_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("frameworks.id", ondelete="SET NULL"),
        nullable=True,
    )
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    inputs_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
