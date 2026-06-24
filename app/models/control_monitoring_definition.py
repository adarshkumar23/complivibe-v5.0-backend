import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ControlMonitoringDefinition(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_monitoring_definitions"
    __table_args__ = (
        Index("ix_control_monitoring_definitions_org_status", "organization_id", "status"),
        Index("ix_control_monitoring_definitions_org_type", "organization_id", "monitoring_type"),
        Index("ix_control_monitoring_definitions_org_control", "organization_id", "control_id"),
        Index("ix_control_monitoring_definitions_org_owner", "organization_id", "owner_user_id"),
        Index("ix_control_monitoring_definitions_org_next_due", "organization_id", "next_check_due_at"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    check_frequency: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_check_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tags_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archive_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
