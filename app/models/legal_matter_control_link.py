import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LegalMatterControlLink(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Many-to-many link between a legal matter and controls.

    Unlike the legacy related_risk_id/related_issue_id single-value columns on
    LegalMatter (a real-world limitation flagged in the G9 walkthrough), a legal
    matter can reference many controls, and the same control can be relevant to
    multiple matters -- hence a proper link table rather than another FK column.
    """

    __tablename__ = "legal_matter_control_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "matter_id", "control_id", name="uq_legal_matter_control_link"),
        Index("ix_legal_matter_control_links_matter_id", "matter_id"),
        Index("ix_legal_matter_control_links_control_id", "control_id"),
        Index("ix_legal_matter_control_links_status", "status"),
    )

    matter_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False)
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
