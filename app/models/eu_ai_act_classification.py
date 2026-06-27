import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EUAIActClassification(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "eu_ai_act_classifications"
    __table_args__ = (
        CheckConstraint(
            "article_category IN ('prohibited', 'high_risk_annex1', 'high_risk_annex3', 'limited_risk', 'minimal_risk')",
            name="ck_eu_ai_act_classifications_category",
        ),
        CheckConstraint(
            "conformity_route IS NULL OR conformity_route IN ('self_assessment', 'notified_body')",
            name="ck_eu_ai_act_classifications_route",
        ),
        UniqueConstraint("ai_system_id", name="uq_eu_ai_act_classifications_system_id"),
        Index("ix_eu_ai_act_classifications_org_category", "organization_id", "article_category"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    article_category: Mapped[str] = mapped_column(String(50), nullable=False)
    annex_reference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    conformity_route: Mapped[str | None] = mapped_column(String(30), nullable=True)
    registration_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    transparency_obligations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    classified_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
