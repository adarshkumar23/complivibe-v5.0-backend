import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AutomationRuleVersion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "automation_rule_versions"
    __table_args__ = (
        Index("ix_automation_rule_versions_org_rule", "organization_id", "rule_id"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("automation_rules.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(64), nullable=False)
    condition_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schedule_config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    version_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
