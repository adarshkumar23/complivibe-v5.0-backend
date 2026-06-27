import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataRetentionPolicy(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_retention_policies"
    __table_args__ = (
        CheckConstraint("action_on_expiry IN ('flag', 'archive', 'delete')", name="ck_data_retention_policies_action_on_expiry"),
        Index("ix_data_retention_policies_org_active", "organization_id", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applies_to_classification_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applies_to_sensitivity_tiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_on_expiry: Mapped[str] = mapped_column(String(20), nullable=False, default="flag")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
