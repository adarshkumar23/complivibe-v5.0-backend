from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class UserSession(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_user_sessions_status"),
        Index("ix_user_sessions_org_user", "organization_id", "user_id"),
        Index("ix_user_sessions_org_status", "organization_id", "status"),
        Index("ix_user_sessions_user_status", "user_id", "status"),
        Index("ix_user_sessions_token_id", "token_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
