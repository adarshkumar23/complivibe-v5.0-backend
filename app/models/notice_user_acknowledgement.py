import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class NoticeUserAcknowledgement(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "notice_user_acknowledgements"
    __table_args__ = (
        UniqueConstraint("notice_id", "user_id", name="uq_notice_ack_notice_user"),
        Index("ix_notice_acks_org_notice", "organization_id", "notice_id"),
        Index("ix_notice_acks_user_time", "user_id", "acknowledged_at"),
    )

    notice_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("privacy_notices.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
