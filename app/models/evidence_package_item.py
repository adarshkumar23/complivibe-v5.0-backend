import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EvidencePackageItem(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_package_items"
    __table_args__ = (
        UniqueConstraint("package_id", "evidence_id", name="uq_evidence_package_items_package_evidence"),
        Index("ix_evidence_package_items_package_id", "package_id"),
        Index("ix_evidence_package_items_package_framework_ref", "package_id", "framework_requirement_ref"),
    )

    package_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_packages.id", ondelete="CASCADE"), nullable=False)
    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="RESTRICT"), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="RESTRICT"), nullable=False)
    framework_requirement_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    added_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
