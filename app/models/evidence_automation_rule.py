import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceAutomationRule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_automation_rules"
    __table_args__ = (
        CheckConstraint(
            "trigger_source IN ('webhook','email','form')",
            name="ck_evidence_automation_rules_source",
        ),
        Index("ix_evidence_automation_rules_org_source", "organization_id", "trigger_source"),
        Index("ix_evidence_automation_rules_org_active", "organization_id", "is_active"),
    )

    trigger_source: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    target_control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    transform_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
