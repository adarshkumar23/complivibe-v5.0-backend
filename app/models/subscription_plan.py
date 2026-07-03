import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPrimaryKeyMixin


class SubscriptionPlan(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "subscription_plans"
    __table_args__ = (UniqueConstraint("plan_code", name="uq_subscription_plans_plan_code"),)

    plan_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    price_inr_monthly: Mapped[int] = mapped_column(Integer, nullable=False)
    price_inr_annual: Mapped[int] = mapped_column(Integer, nullable=False)
    razorpay_plan_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    razorpay_annual_plan_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    max_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_frameworks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_ai_systems: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_dsr_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
