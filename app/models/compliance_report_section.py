import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ComplianceReportSection(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "compliance_report_sections"
    __table_args__ = (
        UniqueConstraint("report_id", "section_key", name="uq_report_section_key"),
        Index("ix_report_sections_org_report", "organization_id", "report_id"),
        Index("ix_report_sections_sort", "report_id", "sort_order"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("compliance_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
