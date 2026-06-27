import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIBOMComponent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "aibom_components"
    __table_args__ = (
        CheckConstraint(
            "component_type IN ('training_data', 'base_model', 'fine_tuning_dataset', 'runtime_data_feed', 'third_party_api', 'framework_library')",
            name="ck_aibom_components_component_type",
        ),
        UniqueConstraint("aibom_id", "component_type", "name", name="uq_aibom_components_type_name"),
        Index("ix_aibom_components_aibom_id", "aibom_id"),
        Index("ix_aibom_components_org_aibom_id", "organization_id", "aibom_id"),
    )

    aibom_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("aibom_records.id", ondelete="CASCADE"), nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_third_party: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_integration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
