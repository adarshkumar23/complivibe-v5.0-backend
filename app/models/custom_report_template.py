import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CustomReportTemplate(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "custom_report_templates"
    __table_args__ = (
        Index("ix_custom_report_templates_org_created_by", "organization_id", "created_by"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sections: Mapped[list[str] | dict] = mapped_column(JSON, nullable=False, default=list)
    framework_filter: Mapped[list[str] | dict | None] = mapped_column(JSON, nullable=True)
    date_range_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
