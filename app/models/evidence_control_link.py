import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceControlLink(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_control_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "evidence_item_id", "control_id", name="uq_evidence_control_link"),
        Index("ix_evidence_control_links_control_id", "control_id"),
        Index("ix_evidence_control_links_evidence_id", "evidence_item_id"),
        Index("ix_evidence_control_links_status", "link_status"),
    )

    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("evidence_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    control_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="CASCADE"),
        nullable=False,
    )
    link_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_confirmed")
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
