import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


DEFAULT_ATTRIBUTE_MAPPING = {
    "email": "NameID",
    "first_name": "firstName",
    "last_name": "lastName",
    "role": "groups",
}


class SSOConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sso_configs"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('okta', 'azure_ad', 'google', 'adfs', 'saml2')",
            name="ck_sso_configs_provider",
        ),
        CheckConstraint(
            "default_role IN ('member', 'reviewer', 'compliance_manager', 'admin', 'owner', 'auditor')",
            name="ck_sso_configs_default_role",
        ),
        Index("ix_sso_configs_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    sso_url: Mapped[str] = mapped_column(Text, nullable=False)
    slo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    certificate: Mapped[str] = mapped_column(Text, nullable=False)
    attribute_mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: dict(DEFAULT_ATTRIBUTE_MAPPING))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    jit_provisioning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_role: Mapped[str] = mapped_column(String(30), nullable=False, default="member")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
