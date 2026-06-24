import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ObligationControlRecommendation(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "obligation_control_recommendations"
    __table_args__ = (
        Index("ix_obl_ctrl_reco_org_framework", "organization_id", "framework_id"),
        Index("ix_obl_ctrl_reco_org_obligation", "organization_id", "obligation_id"),
        Index("ix_obl_ctrl_reco_org_status", "organization_id", "status"),
        Index("ix_obl_ctrl_reco_org_priority", "organization_id", "priority"),
        Index("ix_obl_ctrl_reco_org_type", "organization_id", "recommendation_type"),
        Index("ix_obl_ctrl_reco_org_source", "organization_id", "source"),
        Index("ix_obl_ctrl_reco_org_generated", "organization_id", "generated_at"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("obligation_control_suggestions.id", ondelete="SET NULL"),
        nullable=True,
    )
    recommendation_type: Mapped[str] = mapped_column(String(48), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_control_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommended_control_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    existing_control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_control_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("controls.id", ondelete="SET NULL"),
        nullable=True,
    )
    confidence_level: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic_partial")
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
