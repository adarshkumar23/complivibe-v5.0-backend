import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


DEFAULT_OIDC_SCOPES = ["openid", "email", "profile"]
DEFAULT_OIDC_CLAIM_MAPPING = {
    "email": "email",
    "subject": "sub",
    "name": "name",
}


class OIDCConfig(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "oidc_configs"
    __table_args__ = (
        CheckConstraint(
            "provider IN ('okta', 'azure_ad', 'google', 'auth0', 'oidc')",
            name="ck_oidc_configs_provider",
        ),
        CheckConstraint(
            "default_role IN ('member', 'reviewer', 'compliance_manager', 'admin', 'owner', 'auditor')",
            name="ck_oidc_configs_default_role",
        ),
        Index("ix_oidc_configs_org_active", "organization_id", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="oidc")
    issuer_url: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)
    authorization_endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    token_endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    jwks_uri: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=lambda: list(DEFAULT_OIDC_SCOPES))
    claim_mapping: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: dict(DEFAULT_OIDC_CLAIM_MAPPING))
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
