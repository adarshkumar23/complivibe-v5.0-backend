import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, JSON, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ModelCard(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "model_cards"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_model_cards_status",
        ),
        Index("ix_model_cards_org_system_status", "organization_id", "ai_system_id", "status"),
        Index("ix_model_cards_org_system_version", "organization_id", "ai_system_id", "version"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    intended_purpose: Mapped[str] = mapped_column(Text, nullable=False)
    training_data_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    training_data_cutoff_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    known_limitations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    performance_metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approved_use_cases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    prohibited_use_cases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    bias_evaluation_results: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_oversight_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
