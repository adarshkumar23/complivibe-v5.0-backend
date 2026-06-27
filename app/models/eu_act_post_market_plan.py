import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EUActPostMarketPlan(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "eu_act_post_market_plans"
    __table_args__ = (
        CheckConstraint(
            "reporting_frequency IS NULL OR reporting_frequency IN ('monthly', 'quarterly', 'annually')",
            name="ck_eu_act_post_market_plans_reporting_frequency",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_eu_act_post_market_plans_status",
        ),
        Index("ix_eu_act_post_market_plans_org_system", "organization_id", "ai_system_id"),
        Index("ix_eu_act_post_market_plans_org_status", "organization_id", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    monitoring_metrics: Mapped[list[dict] | list[str]] = mapped_column(JSON, nullable=False, default=list)
    reporting_frequency: Mapped[str | None] = mapped_column(String(50), nullable=True)
    incident_reporting_threshold: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible_person_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
