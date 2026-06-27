import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIRiskSignal(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_risk_signals"
    __table_args__ = (
        CheckConstraint(
            "signal_type IN ('new_training_data_source', 'deployment_scope_expansion', 'model_version_change', 'output_distribution_shift', 'new_use_case', 'new_geographic_deployment', 'high_volume_threshold_exceeded', 'bias_signal')",
            name="ck_ai_risk_signals_signal_type",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low')",
            name="ck_ai_risk_signals_severity",
        ),
        CheckConstraint(
            "status IN ('new', 'reviewed', 'actioned', 'dismissed')",
            name="ck_ai_risk_signals_status",
        ),
        Index("ix_ai_risk_signals_org_system_status", "organization_id", "ai_system_id", "status"),
        Index("ix_ai_risk_signals_org_type", "organization_id", "signal_type"),
        Index("ix_ai_risk_signals_detected_at", "detected_at"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    signal_description: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
