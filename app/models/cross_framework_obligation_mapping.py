import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CrossFrameworkObligationMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cross_framework_obligation_mappings"
    __table_args__ = (
        UniqueConstraint("source_obligation_id", "target_obligation_id", name="uq_cross_framework_source_target"),
        Index("ix_cross_framework_source_obligation_id", "source_obligation_id"),
        Index("ix_cross_framework_target_obligation_id", "target_obligation_id"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    source_obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    target_obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    mapping_type: Mapped[str] = mapped_column(String(30), nullable=False, default="equivalent")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    semantic_similarity_score: Mapped[float | None] = mapped_column(nullable=True)
    mapping_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
