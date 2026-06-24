import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemRiskDimensionTemplate(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_risk_dimension_templates"
    __table_args__ = (
        Index("ix_ai_system_risk_dimension_templates_org_status", "organization_id", "status"),
        Index("ix_ai_system_risk_dimension_templates_org_default", "organization_id", "is_default"),
        Index("ix_ai_system_risk_dimension_templates_org_archived", "organization_id", "archived_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    dimension_weights_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    dimension_thresholds_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    methodology_version: Mapped[str] = mapped_column(String(64), nullable=False, default="manual-dimension-v1")
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
