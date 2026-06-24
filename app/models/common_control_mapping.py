import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CommonControlMapping(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "common_control_mappings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "control_id",
            "framework_id",
            "obligation_id",
            name="uq_common_control_mappings_pair",
        ),
        CheckConstraint(
            "mapping_strength IN ('full', 'partial', 'compensating')",
            name="ck_common_control_mappings_strength",
        ),
        CheckConstraint(
            "status IN ('active', 'inactive', 'under_review')",
            name="ck_common_control_mappings_status",
        ),
        Index("ix_common_control_mappings_org_control", "organization_id", "control_id"),
        Index("ix_common_control_mappings_org_framework", "organization_id", "framework_id"),
        Index("ix_common_control_mappings_org_obligation", "organization_id", "obligation_id"),
        Index("ix_common_control_mappings_org_status", "organization_id", "status"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)

    section_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    mapping_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_strength: Mapped[str] = mapped_column(String(20), nullable=False, default="full")

    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
