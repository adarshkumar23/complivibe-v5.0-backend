import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyDiffGatingProfile(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_policy_diff_gating_profiles"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_diff_gating_profiles_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_diff_gating_profiles_org_created", "organization_id", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    default_severity: Mapped[str] = mapped_column(String(16), nullable=False)
    review_required_threshold: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code_rules_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
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
