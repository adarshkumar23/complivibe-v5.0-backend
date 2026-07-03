import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InboundQuestionnaireSession(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "inbound_questionnaire_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'under_review', 'completed', 'archived')",
            name="ck_inbound_questionnaire_sessions_status",
        ),
        Index("ix_inbound_questionnaire_sessions_org_status", "organization_id", "status"),
        Index("ix_inbound_questionnaire_sessions_org_due_date", "organization_id", "due_date"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    total_questions: Mapped[int] = mapped_column(nullable=False, default=0)
    drafted_count: Mapped[int] = mapped_column(nullable=False, default=0)
    approved_count: Mapped[int] = mapped_column(nullable=False, default=0)
    sent_count: Mapped[int] = mapped_column(nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
