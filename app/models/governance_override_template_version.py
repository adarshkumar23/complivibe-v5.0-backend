import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GovernanceOverrideTemplateVersion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_override_template_versions"
    __table_args__ = (
        Index("ix_override_template_versions_org_template", "organization_id", "template_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_override_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_action: Mapped[str] = mapped_column(String(64), nullable=False)
    default_required_approvals: Mapped[int] = mapped_column(nullable=False)
    approver_role_names_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    condition_rules_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
