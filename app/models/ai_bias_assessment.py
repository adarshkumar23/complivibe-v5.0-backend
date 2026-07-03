import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIBiasAssessment(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_bias_assessments"
    __table_args__ = (
        Index("ix_ai_bias_assessments_org_system", "organization_id", "system_id"),
        Index("ix_ai_bias_assessments_system_assessed", "system_id", "assessed_at"),
        Index("ix_ai_bias_assessments_passed", "passed"),
    )

    system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    assessment_method: Mapped[str] = mapped_column(String(50), nullable=False)
    protected_attribute: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    remediation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    assessed_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
