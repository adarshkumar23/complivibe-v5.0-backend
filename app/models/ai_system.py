import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover - fallback for test environments without pgvector
    class Vector:  # type: ignore[no-redef]
        def __init__(self, *args, **kwargs):
            _ = (args, kwargs)

        def with_variant(self, variant, dialect_name):
            _ = dialect_name
            return variant


class AISystem(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_systems"
    __table_args__ = (
        Index("ix_ai_systems_org_lifecycle", "organization_id", "lifecycle_status"),
        Index("ix_ai_systems_org_system_type", "organization_id", "system_type"),
        Index("ix_ai_systems_org_deployment_status", "organization_id", "deployment_status"),
        Index("ix_ai_systems_org_risk_tier", "organization_id", "risk_tier"),
        Index("ix_ai_systems_org_business_owner", "organization_id", "business_owner_user_id"),
        Index("ix_ai_systems_org_technical_owner", "organization_id", "technical_owner_user_id"),
        Index("ix_ai_systems_org_archived", "organization_id", "archived_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_type: Mapped[str] = mapped_column(String(64), nullable=False)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="proposed")
    deployment_status: Mapped[str] = mapped_column(String(50), nullable=False, default="development")
    risk_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    deployment_environment: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    business_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    technical_owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    vendor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    data_sources_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_population: Mapped[str | None] = mapped_column(Text, nullable=True)
    geographic_scope: Mapped[list[str] | dict | None] = mapped_column(JSON, nullable=True)
    intended_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_case: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_categories_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    user_groups_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    geography_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tags_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384).with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
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
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
