import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EmailTemplate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "email_templates"
    __table_args__ = (
        UniqueConstraint("organization_id", "template_key", "version", name="uq_email_template_org_key_version"),
        Index("ix_email_templates_template_key", "template_key"),
        Index("ix_email_templates_organization_id", "organization_id"),
        Index("ix_email_templates_status", "status"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    template_key: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    subject_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_text_template: Mapped[str] = mapped_column(Text, nullable=False)
    body_html_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    allowed_variables_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
