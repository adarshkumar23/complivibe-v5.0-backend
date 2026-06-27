import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ConsentBannerConfig(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "consent_banner_configs"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_consent_banner_configs_org"),)

    banner_title: Mapped[str] = mapped_column(String(255), nullable=False, default="Cookie Preferences")
    banner_body: Mapped[str] = mapped_column(Text, nullable=False)
    accept_all_text: Mapped[str] = mapped_column(String(100), nullable=False, default="Accept All")
    reject_all_text: Mapped[str] = mapped_column(String(100), nullable=False, default="Reject All")
    manage_text: Mapped[str] = mapped_column(String(100), nullable=False, default="Manage Preferences")
    enabled_categories: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["strictly_necessary", "functional", "analytics", "marketing"],
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
