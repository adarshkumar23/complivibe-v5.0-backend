import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceFreezeWindow(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_freeze_windows"
    __table_args__ = (
        Index("ix_ai_sys_gov_freeze_windows_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_freeze_windows_org_scope", "organization_id", "scope_type"),
        Index("ix_ai_sys_gov_freeze_windows_org_window", "organization_id", "starts_at", "ends_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="all_ai_governance")
    scope_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    enforcement_level: Mapped[str] = mapped_column(String(16), nullable=False, default="block")
    override_allowed: Mapped[bool] = mapped_column(nullable=False, default=True)
    precedence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
