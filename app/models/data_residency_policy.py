import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataResidencyPolicy(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_residency_policies"
    __table_args__ = (
        Index("ix_data_residency_policies_org_active", "organization_id", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_countries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    prohibited_countries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    require_eea_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    require_domestic_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    legal_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to_classification_types: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    applies_to_sensitivity_tiers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
