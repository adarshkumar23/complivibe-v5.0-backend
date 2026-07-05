import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TrainingDataset(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "training_datasets"
    __table_args__ = (
        CheckConstraint(
            "license_type IN ('public_domain', 'creative_commons', 'commercial_license', 'proprietary_internal', 'unclear', 'none')",
            name="ck_training_datasets_license_type",
        ),
        CheckConstraint(
            "consent_basis IS NULL OR consent_basis IN "
            "('explicit_consent', 'legitimate_interest', 'contractual', 'statutory', 'not_applicable', 'unclear')",
            name="ck_training_datasets_consent_basis",
        ),
        Index("ix_training_datasets_org_ai_system", "organization_id", "linked_ai_system_id"),
        Index("ix_training_datasets_org_license_type", "organization_id", "license_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unclear")
    consent_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    linked_ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="RESTRICT"),
        nullable=False,
    )
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
