import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ControlMonitoringResult(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_monitoring_results"
    __table_args__ = (
        Index("ix_control_monitoring_results_org_definition", "organization_id", "definition_id"),
        Index("ix_control_monitoring_results_org_control", "organization_id", "control_id"),
        Index("ix_control_monitoring_results_org_status", "organization_id", "check_status"),
        Index("ix_control_monitoring_results_org_checked", "organization_id", "checked_at"),
    )

    definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("control_monitoring_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    check_status: Mapped[str] = mapped_column(String(32), nullable=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_detail_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    checked_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_check_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
