from sqlalchemy import Boolean, CheckConstraint, Index, JSON, String, Text
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
        # JSON used for sqlite test compatibility while Postgres stores text[] via migration.
        Index("ix_policy_templates_framework_tags", "framework_tags"),
    )

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    framework_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
