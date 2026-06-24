import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MembershipActivationToken(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "membership_activation_tokens"
    __table_args__ = (
        Index("ix_membership_activation_tokens_organization_id", "organization_id"),
        Index("ix_membership_activation_tokens_membership_id", "membership_id"),
        Index("ix_membership_activation_tokens_user_id", "user_id"),
        Index("ix_membership_activation_tokens_status", "status"),
        Index("ix_membership_activation_tokens_expires_at", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    membership_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
