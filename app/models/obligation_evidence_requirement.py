import uuid

from sqlalchemy import Boolean, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ObligationEvidenceRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "obligation_evidence_requirements"
    __table_args__ = (
        Index("ix_obligation_evidence_req_framework", "framework_id"),
        Index("ix_obligation_evidence_req_obligation", "obligation_id"),
        Index("ix_obligation_evidence_req_key", "obligation_id", "requirement_key"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    frequency: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
