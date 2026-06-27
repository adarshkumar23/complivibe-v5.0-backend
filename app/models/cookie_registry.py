import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class CookieRegistry(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "cookie_registries"
    __table_args__ = (
        CheckConstraint(
            "category IN ('strictly_necessary', 'functional', 'analytics', 'marketing', 'unknown')",
            name="ck_cookie_registries_category",
        ),
        CheckConstraint("source IN ('manual', 'scan_report')", name="ck_cookie_registries_source"),
        Index("ix_cookie_registries_org_category", "organization_id", "category"),
        Index("ix_cookie_registries_org_active", "organization_id", "is_active"),
        UniqueConstraint("organization_id", "name", "domain", name="uq_cookie_registry_org_name_domain"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_third_party: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
