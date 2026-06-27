import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIRiskRecommendation(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_risk_recommendations"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('risk_assessment', 'monitoring_breach', 'signal', 'manual')",
            name="ck_ai_risk_recommendations_source_type",
        ),
        CheckConstraint(
            "recommendation_category IN ('technical_control', 'process_control', 'documentation', 'audit', 'decommission')",
            name="ck_ai_risk_recommendations_category",
        ),
        CheckConstraint(
            "priority IN ('critical', 'high', 'medium', 'low')",
            name="ck_ai_risk_recommendations_priority",
        ),
        CheckConstraint(
            "status IN ('active', 'applied', 'dismissed')",
            name="ck_ai_risk_recommendations_status",
        ),
        Index("ix_ai_risk_recommendations_org_system_status", "organization_id", "ai_system_id", "status"),
        Index("ix_ai_risk_recommendations_org_source_type", "organization_id", "source_type"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    recommendation_text: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation_category: Mapped[str] = mapped_column(String(30), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    source_ref_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
