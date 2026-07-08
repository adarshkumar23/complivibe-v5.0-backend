import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OrganizationGovernanceSettingHistory(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "organization_governance_setting_history"
    __table_args__ = (
        Index(
            "ix_org_governance_setting_history_org_version",
            "organization_id",
            "version",
            unique=True,
        ),
        Index(
            "ix_org_governance_setting_history_org_event_created",
            "organization_id",
            "event_type",
            "created_at",
        ),
    )

    version: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    setting_key: Mapped[str] = mapped_column(String(64), nullable=False)
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    affected_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    affected_entity_ids_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    skipped_summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    audit_log_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("audit_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
