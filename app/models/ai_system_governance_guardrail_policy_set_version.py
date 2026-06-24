import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceGuardrailPolicySetVersion(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_guardrail_policy_set_versions"
    __table_args__ = (
        Index("ix_ai_sys_gov_guardrail_policy_versions_org_set", "organization_id", "policy_set_id"),
        Index("ix_ai_sys_gov_guardrail_policy_versions_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_guardrail_policy_versions_org_set_num", "organization_id", "policy_set_id", "version_number"),
    )

    policy_set_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_guardrail_policy_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    profile_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
