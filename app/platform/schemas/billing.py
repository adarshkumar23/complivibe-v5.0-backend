from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BillingSubscribeRequest(BaseModel):
    plan_code: Literal["starter", "growth", "enterprise", "usage_flex"]
    billing_cycle: Literal["monthly", "annual"] = "monthly"


class BillingCancelRequest(BaseModel):
    cancel_at_cycle_end: bool = True


class BillingSubscribeResponse(BaseModel):
    subscription_id: str
    payment_url: str
    plan: str
    billing_cycle: str
    message: str


class BillingStatusResponse(BaseModel):
    subscription_status: str
    plan: str
    is_trial: bool
    trial_days_remaining: int | None
    trial_ends_at: str | None
    subscription_ends_at: str | None
    features: dict[str, Any]
    razorpay_subscription_id: str | None


class BillingInvoiceResponse(BaseModel):
    id: str | None
    amount: float
    currency: str
    status: str | None
    date: int | None
    pdf_url: str | None


class BillingPlanResponse(BaseModel):
    id: uuid.UUID
    plan_code: str
    display_name: str
    plan_type: str
    price_inr_monthly: int
    price_inr_annual: int
    usage_unit_price_inr: float | None = None
    max_users: int | None
    max_frameworks: int | None
    max_ai_systems: int | None
    max_dsr_per_month: int | None
    features: dict[str, Any]
    is_active: bool
    created_at: datetime


class RazorpayWebhookResponse(BaseModel):
    status: str = Field(default="processed")


class UsageSpendCapUpdateRequest(BaseModel):
    usage_spend_cap_enabled: bool
    usage_spend_cap_inr: float | None = Field(default=None, ge=0)


class UsageBillingDashboardRead(BaseModel):
    period_start: str
    period_end: str
    active_frameworks_count: int
    active_users_count: int
    api_calls_count: int
    billable_units: float
    unit_price_inr: float
    current_estimated_cost_inr: float
    projected_month_end_cost_inr: float
    usage_spend_cap_enabled: bool
    usage_spend_cap_inr: float | None = None
    is_spend_cap_breached: bool
    synced_to_processor: bool
    processor_reference: str | None = None


class UsageBillingSyncResponse(BaseModel):
    status: str
    snapshot_id: uuid.UUID
    billable_units: float
    processor_reference: str | None = None
