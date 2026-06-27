import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class OrgEmailConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "org_email_configs"
    __table_args__ = (
        CheckConstraint("provider IN ('ses')", name="ck_org_email_configs_provider"),
        UniqueConstraint("organization_id", name="uq_org_email_configs_org"),
    )

    provider: Mapped[str] = mapped_column(String(20), nullable=False, default="ses")
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    test_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
