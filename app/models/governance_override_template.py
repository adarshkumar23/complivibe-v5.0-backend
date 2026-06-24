import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceOverrideTemplate(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_override_templates"
    __table_args__ = (
        Index("ix_override_templates_org_status", "organization_id", "status"),
        Index("ix_override_templates_org_override_type", "organization_id", "override_type"),
        Index("ix_override_templates_org_target", "organization_id", "target_entity_type"),
        Index("ix_override_templates_org_action", "organization_id", "requested_action"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    default_required_approvals: Mapped[int] = mapped_column(nullable=False, default=2)
    approver_role_names_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    condition_rules_json: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
