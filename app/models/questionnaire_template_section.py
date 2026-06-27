import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class QuestionnaireTemplateSection(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "questionnaire_template_sections"
    __table_args__ = (Index("ix_questionnaire_template_sections_template_order", "template_id", "order_index"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("questionnaire_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
