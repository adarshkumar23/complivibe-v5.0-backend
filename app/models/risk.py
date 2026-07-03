import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Risk(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "risks"
    __table_args__ = (
        Index("ix_risk_org_status", "organization_id", "status"),
        Index("ix_risk_org_severity", "organization_id", "severity"),
        Index("ix_risk_org_category", "organization_id", "category"),
        Index("ix_risk_org_treatment", "organization_id", "treatment_strategy"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="low")
    likelihood: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    impact: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    inherent_score: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    financial_impact: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    brand_impact: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    operational_impact: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    composite_score_method: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    residual_likelihood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_impact: Mapped[int | None] = mapped_column(Integer, nullable=True)
    residual_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="identified")
    treatment_strategy: Mapped[str] = mapped_column(String(32), nullable=False, default="undecided")
    treatment_option: Mapped[str | None] = mapped_column(String(20), nullable=True)
    risk_context_internal: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_context_external: Mapped[str | None] = mapped_column(Text, nullable=True)
    residual_risk_acceptable: Mapped[bool | None] = mapped_column(nullable=True)
    risk_communication_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        "owner_id", Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    target_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acceptance_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    business_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )
