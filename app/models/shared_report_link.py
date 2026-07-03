import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SharedReportLink(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "shared_report_links"
    __table_args__ = (
        Index("ix_shared_report_links_token", "token"),
        Index("ix_shared_report_links_org_creator", "organization_id", "created_by"),
        Index("ix_shared_report_links_exp_active", "expires_at", "is_active"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    report_params: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recipient_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    watermark_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
