import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIRiskClassification(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_risk_classifications"
    __table_args__ = (
        CheckConstraint("risk_tier IN ('prohibited', 'high', 'limited', 'minimal')", name="ck_ai_risk_classifications_tier"),
        CheckConstraint(
            "classification_method IN ('guided', 'manual', 'auto')",
            name="ck_ai_risk_classifications_method",
        ),
        UniqueConstraint("ai_system_id", name="uq_ai_risk_classifications_system_id"),
        Index("ix_ai_risk_classifications_org_tier", "organization_id", "risk_tier"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    risk_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    classification_method: Mapped[str] = mapped_column(String(20), nullable=False)
    classification_basis: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    classified_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_required_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
