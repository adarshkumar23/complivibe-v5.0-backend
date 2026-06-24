import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceReviewPlanConstraint(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_review_plan_constraints"
    __table_args__ = (
        Index("ix_ai_sys_gov_plan_constraints_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_plan_constraints_org_target", "organization_id", "target_review_type"),
        Index("ix_ai_sys_gov_plan_constraints_org_prereq", "organization_id", "prerequisite_review_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    prerequisite_review_type: Mapped[str] = mapped_column(String(64), nullable=False)
    constraint_type: Mapped[str] = mapped_column(String(32), nullable=False)
    enforcement_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    min_gap_days: Mapped[int | None] = mapped_column(nullable=True)
    max_gap_days: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
