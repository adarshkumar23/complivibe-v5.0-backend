import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ShadowAIDetection(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "shadow_ai_detections"
    __table_args__ = (
        CheckConstraint(
            "detection_method IN ('questionnaire', 'manual_report', 'integration_analysis', 'network_scan')",
            name="ck_shadow_ai_detections_detection_method",
        ),
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="ck_shadow_ai_detections_confidence"),
        CheckConstraint(
            "status IN ('new', 'under_review', 'registered', 'dismissed')",
            name="ck_shadow_ai_detections_status",
        ),
        Index("ix_shadow_ai_detections_org_status", "organization_id", "status"),
        Index("ix_shadow_ai_detections_org_detected_name", "organization_id", "detected_name"),
    )

    detected_name: Mapped[str] = mapped_column(String(255), nullable=False)
    detection_method: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="SET NULL"),
        nullable=True,
    )
    reported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
