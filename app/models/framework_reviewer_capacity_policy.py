import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkReviewerCapacityPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "framework_reviewer_capacity_policies"
    __table_args__ = (
        Index("ix_framework_reviewer_capacity_policies_org_status", "organization_id", "status"),
        Index("ix_framework_reviewer_capacity_policies_org_role", "organization_id", "role_name"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    max_active_assignments: Mapped[int] = mapped_column(nullable=False, default=0)
    max_overdue_assignments: Mapped[int] = mapped_column(nullable=False, default=0)
    preferred_review_types_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    preferred_target_coverage_levels_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
