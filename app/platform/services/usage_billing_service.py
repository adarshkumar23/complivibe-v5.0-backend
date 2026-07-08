from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.organization_framework import OrganizationFramework
from app.models.subscription_plan import SubscriptionPlan
from app.models.usage_billing_snapshot import UsageBillingSnapshot
from app.platform.services.razorpay_service import RazorpayService
from app.services.audit_service import AuditService


class UsageBillingService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.rzp = RazorpayService()
        self.audit = AuditService(db)

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def _month_bounds(now: date) -> tuple[date, date]:
        start = now.replace(day=1)
        if now.month == 12:
            next_month = date(now.year + 1, 1, 1)
        else:
            next_month = date(now.year, now.month + 1, 1)
        end = date.fromordinal(next_month.toordinal() - 1)
        return start, end

    @staticmethod
    def _to_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _active_subscription_plan(self, organization: Organization) -> SubscriptionPlan:
        plan = self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.plan_code == organization.subscription_plan,
                SubscriptionPlan.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active subscription plan is not configured")
        return plan

    def _usage_counts(self, organization_id: UUID, period_start: date, period_end: date) -> tuple[int, int, int]:
        frameworks = int(
            self.db.execute(
                select(func.count(OrganizationFramework.id)).where(
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                )
            ).scalar_one()
        )
        users = int(
            self.db.execute(
                select(func.count(Membership.id)).where(
                    Membership.organization_id == organization_id,
                    Membership.status == "active",
                )
            ).scalar_one()
        )
        api_calls = int(
            self.db.execute(
                select(func.count(AuditLog.id)).where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.created_at >= datetime.combine(period_start, datetime.min.time(), tzinfo=UTC),
                    AuditLog.created_at <= datetime.combine(period_end, datetime.max.time(), tzinfo=UTC),
                )
            ).scalar_one()
        )
        return frameworks, users, api_calls

    @staticmethod
    def _weights(plan: SubscriptionPlan) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        raw = plan.usage_weights_json or {}
        framework_weight = Decimal(str(raw.get("active_framework_weight", 2.0)))
        user_weight = Decimal(str(raw.get("active_user_weight", 1.0)))
        api_calls_per_unit = Decimal(str(raw.get("api_calls_per_unit", 1000.0)))
        api_call_weight = Decimal(str(raw.get("api_call_weight", 0.5)))
        if api_calls_per_unit <= 0:
            api_calls_per_unit = Decimal("1000")
        return framework_weight, user_weight, api_calls_per_unit, api_call_weight

    def _build_snapshot(self, organization: Organization) -> UsageBillingSnapshot:
        today = datetime.now(UTC).date()
        period_start, period_end = self._month_bounds(today)
        plan = self._active_subscription_plan(organization)
        frameworks, users, api_calls = self._usage_counts(organization.id, period_start, period_end)

        unit_price = Decimal(str(plan.usage_unit_price_inr or 0))
        fw_weight, user_weight, api_calls_per_unit, api_weight = self._weights(plan)
        billable_units = (
            Decimal(frameworks) * fw_weight
            + Decimal(users) * user_weight
            + (Decimal(api_calls) / api_calls_per_unit) * api_weight
        )
        billable_units = self._round(billable_units)

        current_estimated_cost = self._round(billable_units * unit_price)
        elapsed_days = max(1, (today - period_start).days + 1)
        total_days = (period_end - period_start).days + 1
        projected_month_end_cost = self._round((current_estimated_cost / Decimal(elapsed_days)) * Decimal(total_days))

        spend_cap = Decimal(str(organization.usage_spend_cap_inr)) if organization.usage_spend_cap_inr is not None else None
        # The usage spend cap is intentionally a SOFT cap. It is a warning/notification
        # guardrail, not a kill switch. Customers continue to have full product access
        # mid-work; the only automatic side effect is that usage is NOT synced to the
        # payment processor while the cap is breached.
        breached = bool(organization.usage_spend_cap_enabled and spend_cap is not None and projected_month_end_cost > spend_cap)

        snapshot = UsageBillingSnapshot(
            organization_id=organization.id,
            subscription_plan_id=plan.id,
            period_start=period_start,
            period_end=period_end,
            active_frameworks_count=frameworks,
            active_users_count=users,
            api_calls_count=api_calls,
            billable_units=billable_units,
            unit_price_inr=unit_price,
            current_estimated_cost_inr=current_estimated_cost,
            projected_month_end_cost_inr=projected_month_end_cost,
            spend_cap_inr=spend_cap,
            is_spend_cap_breached=breached,
            synced_to_processor=False,
            source_inputs_json={
                "weights": {
                    "active_framework_weight": float(fw_weight),
                    "active_user_weight": float(user_weight),
                    "api_calls_per_unit": float(api_calls_per_unit),
                    "api_call_weight": float(api_weight),
                },
                "plan_type": plan.plan_type,
            },
        )
        self.db.add(snapshot)
        self.db.flush()
        return snapshot

    @staticmethod
    def _spend_cap_alert(snapshot: UsageBillingSnapshot) -> str | None:
        if not snapshot.is_spend_cap_breached:
            return None
        return (
            f"Spend cap breached: projected month-end cost "
            f"INR {float(snapshot.projected_month_end_cost_inr):,.2f} exceeds the configured cap "
            f"INR {float(snapshot.spend_cap_inr):,.2f}. This is a soft warning only — "
            "your team can continue using CompliVibe. Usage sync to the payment "
            "processor is paused until the cap is raised or usage drops."
        )

    def _previous_period_snapshot(self, organization_id: UUID, period_start: date) -> UsageBillingSnapshot | None:
        if period_start.month == 1:
            prev_period_start = date(period_start.year - 1, 12, 1)
        else:
            prev_period_start = date(period_start.year, period_start.month - 1, 1)
        return self.db.execute(
            select(UsageBillingSnapshot)
            .where(
                UsageBillingSnapshot.organization_id == organization_id,
                UsageBillingSnapshot.period_start == prev_period_start,
            )
            .order_by(UsageBillingSnapshot.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _cost_trend(current_cost: Decimal, previous_cost: Decimal | None) -> str:
        if previous_cost is None:
            return "no_prior_period_data"
        if previous_cost == 0:
            return "increasing" if current_cost > 0 else "flat"
        change_ratio = (current_cost - previous_cost) / previous_cost
        if change_ratio > Decimal("0.05"):
            return "increasing"
        if change_ratio < Decimal("-0.05"):
            return "decreasing"
        return "flat"

    def _snapshot_payload(self, snapshot: UsageBillingSnapshot, organization: Organization, plan: SubscriptionPlan | None) -> dict:
        context_flags: list[str] = []
        is_usage_based_plan = plan is not None and plan.plan_type == "usage_based"
        if plan is None:
            context_flags.append("subscription_plan_missing")
        elif not is_usage_based_plan:
            context_flags.append("estimated_cost_not_billable_fixed_plan")

        previous_snapshot = self._previous_period_snapshot(organization.id, snapshot.period_start)
        previous_period_cost = (
            Decimal(str(previous_snapshot.projected_month_end_cost_inr)) if previous_snapshot is not None else None
        )
        cost_trend = self._cost_trend(Decimal(str(snapshot.projected_month_end_cost_inr)), previous_period_cost)
        if cost_trend == "no_prior_period_data":
            context_flags.append("no_prior_period_comparison")

        if (
            snapshot.active_frameworks_count == 0
            and snapshot.active_users_count == 0
            and snapshot.api_calls_count == 0
        ):
            context_flags.append("zero_usage_period")

        if (
            snapshot.synced_to_processor
            and previous_snapshot is not None
            and previous_snapshot.synced_to_processor
            and float(previous_snapshot.billable_units) != float(snapshot.billable_units)
        ):
            context_flags.append("usage_changed_since_last_sync")

        return {
            "period_start": snapshot.period_start.isoformat(),
            "period_end": snapshot.period_end.isoformat(),
            "active_frameworks_count": snapshot.active_frameworks_count,
            "active_users_count": snapshot.active_users_count,
            "api_calls_count": snapshot.api_calls_count,
            "billable_units": float(snapshot.billable_units),
            "unit_price_inr": float(snapshot.unit_price_inr),
            "current_estimated_cost_inr": float(snapshot.current_estimated_cost_inr),
            "projected_month_end_cost_inr": float(snapshot.projected_month_end_cost_inr),
            "usage_spend_cap_enabled": organization.usage_spend_cap_enabled,
            "usage_spend_cap_inr": float(organization.usage_spend_cap_inr) if organization.usage_spend_cap_inr is not None else None,
            "is_spend_cap_breached": snapshot.is_spend_cap_breached,
            "spend_cap_alert": self._spend_cap_alert(snapshot),
            "synced_to_processor": snapshot.synced_to_processor,
            "processor_reference": snapshot.processor_reference,
            "is_usage_based_plan": is_usage_based_plan,
            "previous_period_cost_inr": float(previous_period_cost) if previous_period_cost is not None else None,
            "cost_trend": cost_trend,
            "context_flags": sorted(set(context_flags)),
        }

    def usage_dashboard(self, organization_id: UUID, actor_user_id: UUID | None) -> dict:
        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        snapshot = self._build_snapshot(organization)
        self.audit.write_audit_log(
            action="billing.usage_dashboard_viewed",
            entity_type="usage_billing_snapshots",
            entity_id=snapshot.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "billable_units": float(snapshot.billable_units),
                "projected_month_end_cost_inr": float(snapshot.projected_month_end_cost_inr),
            },
            metadata_json={"source": "billing.usage.dashboard"},
        )
        plan = self.db.get(SubscriptionPlan, snapshot.subscription_plan_id)
        return self._snapshot_payload(snapshot, organization, plan)

    def update_spend_cap(
        self,
        organization_id: UUID,
        actor_user_id: UUID,
        *,
        usage_spend_cap_enabled: bool,
        usage_spend_cap_inr: float | None,
    ) -> dict:
        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
        if usage_spend_cap_enabled and usage_spend_cap_inr is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="usage_spend_cap_inr is required when spend cap is enabled")

        before = {
            "usage_spend_cap_enabled": organization.usage_spend_cap_enabled,
            "usage_spend_cap_inr": float(organization.usage_spend_cap_inr) if organization.usage_spend_cap_inr is not None else None,
        }
        organization.usage_spend_cap_enabled = usage_spend_cap_enabled
        organization.usage_spend_cap_inr = Decimal(str(usage_spend_cap_inr)) if usage_spend_cap_inr is not None else None
        self.db.flush()

        self.audit.write_audit_log(
            action="billing.usage_spend_cap_updated",
            entity_type="organizations",
            entity_id=organization_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={
                "usage_spend_cap_enabled": organization.usage_spend_cap_enabled,
                "usage_spend_cap_inr": float(organization.usage_spend_cap_inr) if organization.usage_spend_cap_inr is not None else None,
            },
            metadata_json={"source": "billing.usage.spend_cap"},
        )
        return {
            "usage_spend_cap_enabled": organization.usage_spend_cap_enabled,
            "usage_spend_cap_inr": float(organization.usage_spend_cap_inr) if organization.usage_spend_cap_inr is not None else None,
        }

    def sync_usage_to_processor(self, organization_id: UUID, actor_user_id: UUID) -> dict:
        organization = self.db.get(Organization, organization_id)
        if organization is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

        snapshot = self._build_snapshot(organization)
        if snapshot.is_spend_cap_breached:
            self.audit.write_audit_log(
                action="billing.usage_sync_blocked_spend_cap",
                entity_type="usage_billing_snapshots",
                entity_id=snapshot.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={
                    "projected_month_end_cost_inr": float(snapshot.projected_month_end_cost_inr),
                    "spend_cap_inr": float(snapshot.spend_cap_inr) if snapshot.spend_cap_inr is not None else None,
                },
                metadata_json={"reason": "spend_cap_breached"},
            )
            return {
                "status": "blocked_spend_cap",
                "snapshot_id": snapshot.id,
                "billable_units": float(snapshot.billable_units),
                "spend_cap_alert": self._spend_cap_alert(snapshot),
                "processor_reference": None,
            }

        if not organization.razorpay_subscription_id:
            self.audit.write_audit_log(
                action="billing.usage_sync_skipped_missing_subscription",
                entity_type="usage_billing_snapshots",
                entity_id=snapshot.id,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                after_json={"billable_units": float(snapshot.billable_units)},
                metadata_json={"reason": "missing_razorpay_subscription_id"},
            )
            return {
                "status": "missing_subscription",
                "snapshot_id": snapshot.id,
                "billable_units": float(snapshot.billable_units),
                "processor_reference": None,
            }

        qty = max(1, int(Decimal(str(snapshot.billable_units)).to_integral_value(rounding=ROUND_HALF_UP)))
        processor_result = self.rzp.update_subscription_quantity(organization.razorpay_subscription_id, quantity=qty)

        snapshot.synced_to_processor = True
        snapshot.processor_reference = str(processor_result.get("id") or organization.razorpay_subscription_id)
        self.db.flush()

        self.audit.write_audit_log(
            action="billing.usage_synced_to_processor",
            entity_type="usage_billing_snapshots",
            entity_id=snapshot.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            after_json={
                "billable_units": float(snapshot.billable_units),
                "processor_quantity": qty,
                "processor_reference": snapshot.processor_reference,
            },
            metadata_json={"source": "razorpay.subscription.edit"},
        )
        return {
            "status": "synced",
            "snapshot_id": snapshot.id,
            "billable_units": float(snapshot.billable_units),
            "processor_reference": snapshot.processor_reference,
        }
