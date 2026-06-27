import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvidencePackage(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_packages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'assembled', 'exported', 'archived')",
            name="ck_evidence_packages_status",
        ),
        Index("ix_evidence_packages_org_engagement", "organization_id", "audit_engagement_id"),
        Index("ix_evidence_packages_org_status", "organization_id", "status"),
    )

    audit_engagement_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("audit_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope_framework_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cover_sheet_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    chain_of_custody: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    assembled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assembled_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
