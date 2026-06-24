import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class CommonControlEvidenceCoverage(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "common_control_evidence_coverage"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "control_id",
            "evidence_id",
            "mapping_id",
            name="uq_common_control_evidence_coverage",
        ),
        CheckConstraint(
            "coverage_status IN ('covers', 'partial', 'insufficient')",
            name="ck_common_control_evidence_coverage_status",
        ),
        Index("ix_common_control_evidence_coverage_org_control", "organization_id", "control_id"),
        Index("ix_common_control_evidence_coverage_org_evidence", "organization_id", "evidence_id"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    mapping_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("common_control_mappings.id", ondelete="CASCADE"), nullable=False)

    coverage_status: Mapped[str] = mapped_column(String(20), nullable=False)
    coverage_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    assessed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
