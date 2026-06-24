import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemControlLink(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_control_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "ai_system_id", "control_id", name="uq_ai_system_control_link"),
        Index("ix_ai_system_control_links_ai_system_id", "ai_system_id"),
        Index("ix_ai_system_control_links_control_id", "control_id"),
        Index("ix_ai_system_control_links_status", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    link_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    unlinked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlink_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
