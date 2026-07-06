import uuid
from datetime import date

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UsageBillingSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "usage_billing_snapshots"
    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="ck_usage_billing_snapshots_period_range"),
        CheckConstraint("active_frameworks_count >= 0", name="ck_usage_billing_snapshots_frameworks"),
        CheckConstraint("active_users_count >= 0", name="ck_usage_billing_snapshots_users"),
        CheckConstraint("api_calls_count >= 0", name="ck_usage_billing_snapshots_api_calls"),
        CheckConstraint("billable_units >= 0", name="ck_usage_billing_snapshots_billable_units"),
        Index("ix_usage_billing_snapshots_org_period_start", "organization_id", "period_start"),
        Index("ix_usage_billing_snapshots_org_created_at", "organization_id", "created_at"),
        Index("ix_usage_billing_snapshots_synced", "organization_id", "synced_to_processor"),
    )

    subscription_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    active_frameworks_count: Mapped[int] = mapped_column(nullable=False, default=0)
    active_users_count: Mapped[int] = mapped_column(nullable=False, default=0)
    api_calls_count: Mapped[int] = mapped_column(nullable=False, default=0)
    billable_units: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    unit_price_inr: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    current_estimated_cost_inr: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    projected_month_end_cost_inr: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    spend_cap_inr: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    is_spend_cap_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    synced_to_processor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processor_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_inputs_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
