import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceOverrideRequest(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_override_requests"
    __table_args__ = (
        Index("ix_override_requests_org_status", "organization_id", "status"),
        Index("ix_override_requests_org_type", "organization_id", "override_type"),
        Index("ix_override_requests_org_target", "organization_id", "target_entity_type", "target_entity_id"),
        Index("ix_override_requests_org_template", "organization_id", "template_id"),
    )

    override_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    requested_action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("governance_override_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    template_version: Mapped[int | None] = mapped_column(nullable=True)
    required_approvals: Mapped[int] = mapped_column(nullable=False, default=2)
    approval_count: Mapped[int] = mapped_column(nullable=False, default=0)
    rejection_count: Mapped[int] = mapped_column(nullable=False, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    routing_context_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    approver_role_names_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
