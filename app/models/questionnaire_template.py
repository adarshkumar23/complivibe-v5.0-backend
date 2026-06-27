import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class QuestionnaireTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "questionnaire_templates"
    __table_args__ = (
        CheckConstraint(
            "template_type IN ('sig_lite', 'caiq', 'custom')",
            name="ck_questionnaire_templates_template_type",
        ),
        Index("ix_questionnaire_templates_org_active", "organization_id", "is_active"),
        Index("ix_questionnaire_templates_type_system", "template_type", "is_system_template"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    template_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False, default="1.0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
