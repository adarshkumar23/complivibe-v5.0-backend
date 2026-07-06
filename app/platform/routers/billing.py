from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.role import Role
from app.models.user import User
from app.platform.schemas.billing import (
    BillingCancelRequest,
    BillingInvoiceResponse,
    BillingPlanResponse,
    BillingStatusResponse,
    BillingSubscribeRequest,
    BillingSubscribeResponse,
    RazorpayWebhookResponse,
    UsageBillingDashboardRead,
    UsageBillingSyncResponse,
    UsageSpendCapUpdateRequest,
)
from app.platform.services.billing_service import BillingService
from app.platform.services.razorpay_service import RazorpayService
from app.platform.services.usage_billing_service import UsageBillingService
from app.platform.services.webhook_handler_service import WebhookHandlerService

router = APIRouter(prefix="/billing", tags=["billing"])
webhook_router = APIRouter(prefix="/api/webhook", tags=["billing-webhook"])


def _require_admin_membership(db: Session, membership: Membership) -> None:
    role = db.execute(select(Role).where(Role.id == membership.role_id)).scalar_one_or_none()
    if role is None or role.name not in {"owner", "admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Org admin role required")


@router.post("/subscribe", response_model=BillingSubscribeResponse)
def subscribe(
    payload: BillingSubscribeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> BillingSubscribeResponse:
    _require_admin_membership(db, membership)
    result = BillingService(db).initiate_subscription(
        org_id=organization.id,
        plan_code=payload.plan_code,
        admin_user_id=current_user.id,
        billing_cycle=payload.billing_cycle,
    )
    db.commit()
    return BillingSubscribeResponse(**result)


@router.get("/status", response_model=BillingStatusResponse)
def billing_status(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("org:read")),
) -> BillingStatusResponse:
    result = BillingService(db).get_billing_status(organization.id)
    return BillingStatusResponse(**result)


@router.get("/plans", response_model=list[BillingPlanResponse])
def list_plans(db: Session = Depends(get_db)) -> list[BillingPlanResponse]:
    service = BillingService(db)
    plans = service.list_plans()
    db.commit()
    return [
        BillingPlanResponse(
            id=item.id,
            plan_code=item.plan_code,
            display_name=item.display_name,
            plan_type=item.plan_type,
            price_inr_monthly=item.price_inr_monthly,
            price_inr_annual=item.price_inr_annual,
            usage_unit_price_inr=float(item.usage_unit_price_inr) if item.usage_unit_price_inr is not None else None,
            max_users=item.max_users,
            max_frameworks=item.max_frameworks,
            max_ai_systems=item.max_ai_systems,
            max_dsr_per_month=item.max_dsr_per_month,
            features=item.features or {},
            is_active=item.is_active,
            created_at=item.created_at,
        )
        for item in plans
    ]


@router.post("/cancel")
def cancel(
    payload: BillingCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:update")),
) -> dict:
    _require_admin_membership(db, membership)
    result = BillingService(db).cancel_subscription(
        org_id=organization.id,
        user_id=current_user.id,
        cancel_at_cycle_end=payload.cancel_at_cycle_end,
    )
    db.commit()
    return result


@router.get("/invoices", response_model=list[BillingInvoiceResponse])
def invoices(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("org:read")),
) -> list[BillingInvoiceResponse]:
    _require_admin_membership(db, membership)
    result = BillingService(db).get_invoices(organization.id)
    return [BillingInvoiceResponse(**item) for item in result]


@router.get("/usage/dashboard", response_model=UsageBillingDashboardRead)
def usage_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("billing_usage_dashboard:read")),
) -> UsageBillingDashboardRead:
    _require_admin_membership(db, membership)
    payload = UsageBillingService(db).usage_dashboard(organization.id, current_user.id)
    db.commit()
    return UsageBillingDashboardRead(**payload)


@router.post("/usage/spend-cap")
def update_usage_spend_cap(
    payload: UsageSpendCapUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("billing_usage_spend_cap:write")),
) -> dict:
    _require_admin_membership(db, membership)
    result = UsageBillingService(db).update_spend_cap(
        organization.id,
        current_user.id,
        usage_spend_cap_enabled=payload.usage_spend_cap_enabled,
        usage_spend_cap_inr=payload.usage_spend_cap_inr,
    )
    db.commit()
    return result


@router.post("/usage/sync", response_model=UsageBillingSyncResponse)
def sync_usage_to_processor(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    membership: Membership = Depends(require_permission("billing_usage_sync:execute")),
) -> UsageBillingSyncResponse:
    _require_admin_membership(db, membership)
    result = UsageBillingService(db).sync_usage_to_processor(organization.id, current_user.id)
    db.commit()
    return UsageBillingSyncResponse(**result)


@webhook_router.post("/razorpay", response_model=RazorpayWebhookResponse)
async def razorpay_webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
) -> RazorpayWebhookResponse:
    if not x_razorpay_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Razorpay-Signature header")

    raw_body = await request.body()
    if not RazorpayService().verify_webhook_signature(raw_body, x_razorpay_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook payload") from exc

    handler_result = WebhookHandlerService(db).handle(payload=payload, razorpay_event_id=x_razorpay_event_id)
    db.commit()
    return RazorpayWebhookResponse(status=handler_result.get("status", "processed"))
