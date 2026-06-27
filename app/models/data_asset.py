import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataAsset(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_assets"
    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('database', 'file_store', 'data_stream', 'api', 'data_lake', 'table', 'schema', 'bucket', 'other')",
            name="ck_data_assets_asset_type",
        ),
        CheckConstraint(
            "sensitivity_tier IS NULL OR sensitivity_tier IN ('public', 'internal', 'confidential', 'restricted', 'secret')",
            name="ck_data_assets_sensitivity_tier",
        ),
        CheckConstraint(
            "classification_type IS NULL OR classification_type IN ('personal_data', 'sensitive_personal_data', 'financial_data', 'health_data', 'intellectual_property', 'operational_data', 'public_data', 'unclassified')",
            name="ck_data_assets_classification_type",
        ),
        CheckConstraint(
            "classification_source IS NULL OR classification_source IN ('metadata_rules', 'presidio_sample', 'manual')",
            name="ck_data_assets_classification_source",
        ),
        CheckConstraint(
            "classification_confidence IS NULL OR (classification_confidence >= 0 AND classification_confidence <= 1)",
            name="ck_data_assets_classification_confidence",
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'under_review', 'decommissioned')",
            name="ck_data_assets_status",
        ),
        Index("ix_data_assets_org_asset_type", "organization_id", "asset_type"),
        Index("ix_data_assets_org_sensitivity", "organization_id", "sensitivity_tier"),
        Index("ix_data_assets_org_classification_type", "organization_id", "classification_type"),
        Index("ix_data_assets_org_status", "organization_id", "status"),
        Index("ix_data_assets_org_classification_confirmed", "organization_id", "classification_confirmed"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    custodian_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sensitivity_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    classification_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 2), nullable=True)
    classification_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    geographic_locations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    permitted_regions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    schema_column_names: Mapped[list | None] = mapped_column(JSON, nullable=True)
    retention_policy_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retention_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_volume_estimate: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_system: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
