import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemRiskClassificationRecord(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_risk_classification_records"
    __table_args__ = (
        Index("ix_ai_risk_classification_records_org_assessment", "organization_id", "risk_assessment_id"),
        Index("ix_ai_risk_classification_records_org_ai_system", "organization_id", "ai_system_id"),
        Index("ix_ai_risk_classification_records_org_status", "organization_id", "status"),
        Index("ix_ai_risk_classification_records_org_confidence", "organization_id", "confidence_level"),
        Index("ix_ai_risk_classification_records_org_source", "organization_id", "source_type"),
        Index("ix_ai_risk_classification_records_org_archived", "organization_id", "archived_at"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    taxonomy_template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_classification_taxonomy_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    taxonomy_template_snapshot_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    classification_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    confidence_level: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_submitted")
    review_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_request_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    control_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risk_ids_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
