import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OrganizationAIConfiguration(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "organization_ai_configurations"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_ai_cfg_org"),
    )

    use_byo_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    groq_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    azure_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    azure_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    azure_deployment_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
