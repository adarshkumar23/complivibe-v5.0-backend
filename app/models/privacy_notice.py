import uuid
from datetime import date, datetime

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class PrivacyNotice(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "privacy_notices"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_privacy_notices_status"),
        Index("ix_privacy_notices_org_status", "organization_id", "status"),
        Index("ix_privacy_notices_org_lang_status", "organization_id", "language", "status"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    frameworks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
