import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIBOMRecord(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "aibom_records"
    __table_args__ = (
        Index("ix_aibom_records_org_system", "organization_id", "ai_system_id"),
        Index("ix_aibom_records_org_system_version", "organization_id", "ai_system_id", "version"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
