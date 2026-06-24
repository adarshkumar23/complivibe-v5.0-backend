import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TechnicalControlRule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "technical_control_rules"
    __table_args__ = (
        CheckConstraint(
            "target_resource_type IN ('aws_s3', 'aws_iam', 'aws_ec2', 'aws_rds', 'gcp_iam', 'gcp_storage', 'azure_ad', 'azure_storage', 'network', 'os', 'generic')",
            name="ck_technical_control_rules_target_resource_type",
        ),
        CheckConstraint(
            "evaluation_operator IN ('equals', 'not_equals', 'contains', 'not_contains', 'gte', 'lte', 'is_true', 'is_false', 'exists', 'not_exists')",
            name="ck_technical_control_rules_evaluation_operator",
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_technical_control_rules_severity",
        ),
        Index("ix_technical_control_rules_org_control", "organization_id", "control_id"),
        Index("ix_technical_control_rules_org_active", "organization_id", "is_active"),
    )

    control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_config_key: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_config_value: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_operator: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
