import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EscalationPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "escalation_policies"
    __table_args__ = (
        CheckConstraint(
            "entity_type IN ('issue', 'risk', 'vendor_mitigation', 'control_exception', 'pbc_request')",
            name="ck_escalation_policies_entity_type",
        ),
        CheckConstraint(
            "condition_type IN ('time_in_state', 'sla_breach', 'severity_threshold')",
            name="ck_escalation_policies_condition_type",
        ),
        Index("ix_escalation_policies_org_entity_active", "organization_id", "entity_type", "is_active"),
        Index("ix_escalation_policies_org_active", "organization_id", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(50), nullable=False)
    condition_value: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    escalate_to_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    notification_message_template: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
