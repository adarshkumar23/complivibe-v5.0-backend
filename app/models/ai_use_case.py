import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AIUseCase(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_use_cases"
    __table_args__ = (
        CheckConstraint(
            "use_case_type IN ('decision_making', 'classification', 'generation', 'recommendation', 'monitoring', 'automation', 'other')",
            name="ck_ai_use_cases_use_case_type",
        ),
        Index("ix_ai_use_cases_org_system", "organization_id", "ai_system_id"),
        Index("ix_ai_use_cases_org_high_stakes", "organization_id", "is_high_stakes"),
        Index("ix_ai_use_cases_org_type", "organization_id", "use_case_type"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    use_case_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_high_stakes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    affected_groups: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployment_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
