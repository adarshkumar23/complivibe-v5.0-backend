import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ControlTestRun(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "control_test_runs"
    __table_args__ = (
        Index("ix_control_test_runs_org_test", "organization_id", "control_test_definition_id"),
        Index("ix_control_test_runs_org_control", "organization_id", "control_id"),
        Index("ix_control_test_runs_org_created", "organization_id", "created_at"),
    )

    control_test_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("control_test_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    result_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_key: Mapped[str] = mapped_column(String(64), nullable=False)
    executed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    execution_source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    evidence_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("evidence_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
