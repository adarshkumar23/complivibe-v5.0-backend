import uuid

from sqlalchemy import ARRAY, Boolean, CheckConstraint, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class PolicyTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "policy_templates"
    __table_args__ = (
        CheckConstraint(
            "category IN ('Security', 'Privacy', 'Operations', 'HR', 'Legal', 'AI Governance', 'Compliance')",
            name="ck_policy_templates_category",
        ),
        Index("ix_policy_templates_category", "category"),
        Index("ix_policy_templates_is_active", "is_active"),
        Index("ix_policy_templates_organization_id", "organization_id"),
        Index("ix_policy_templates_policy_type", "policy_type"),
        Index("ix_policy_templates_is_system_is_active", "is_system", "is_active"),
        Index("ix_policy_templates_framework_tags", "framework_tags"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Real Postgres text[] per migration 0101 (grandfathered ARRAY exception); JSON on
    # sqlite only, since sqlite has no native array type.
    framework_tags: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON, "sqlite"), nullable=False, default=list
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
