import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CustomReportTemplate(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "custom_report_templates"
    __table_args__ = (
        Index("ix_custom_report_templates_org_created_by", "organization_id", "created_by"),
        Index("ix_custom_report_templates_org_type", "organization_id", "template_type"),
        Index(
            "uq_custom_report_templates_org_system_key_active",
            "organization_id",
            "system_template_key",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND system_template_key IS NOT NULL"),
            sqlite_where=text("deleted_at IS NULL AND system_template_key IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template_type: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    system_template_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sections: Mapped[list[str] | dict] = mapped_column(JSON, nullable=False, default=list)
    disclosure_structure: Mapped[list[dict] | dict | None] = mapped_column(JSON, nullable=True)
    framework_filter: Mapped[list[str] | dict | None] = mapped_column(JSON, nullable=True)
    date_range_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
