import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class LegalMatterEvidenceLink(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Many-to-many link between a legal matter and evidence items.

    Unlike the legacy related_risk_id/related_issue_id single-value columns on
    LegalMatter (a real-world limitation flagged in the G9 walkthrough), a legal
    matter can reference many evidence items, and the same evidence item can support
    multiple matters -- hence a proper link table rather than another FK column.
    """

    __tablename__ = "legal_matter_evidence_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "matter_id", "evidence_id", name="uq_legal_matter_evidence_link"),
        Index("ix_legal_matter_evidence_links_matter_id", "matter_id"),
        Index("ix_legal_matter_evidence_links_evidence_id", "evidence_id"),
        Index("ix_legal_matter_evidence_links_status", "status"),
    )

    matter_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("legal_matters.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    linked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
