import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ISO42001ConformityTracker(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "iso42001_conformity_trackers"
    __table_args__ = (
        CheckConstraint(
            "implementation_status IN ('not_started', 'in_progress', 'implemented', 'verified')",
            name="ck_iso42001_conformity_trackers_status",
        ),
        UniqueConstraint("organization_id", "clause_ref", name="uq_iso42001_conformity_trackers_org_clause"),
        Index("ix_iso42001_conformity_trackers_org_clause", "organization_id", "clause_ref"),
    )

    clause_ref: Mapped[str] = mapped_column(String(20), nullable=False)
    implementation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_started")
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
