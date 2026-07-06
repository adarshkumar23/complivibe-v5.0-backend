from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.roi_calculator_lead import ROICalculatorLead
from app.models.subscription_plan import SubscriptionPlan
from app.schemas.roi_calculator import ROICalculatorRequest
from app.services.audit_service import AuditService

PUBLIC_ROI_ORG_SLUG = "public-roi-leads"
PUBLIC_ROI_ORG_NAME = "Public ROI Calculator Leads"

# Methodology sources used by this model:
# 1) McKinsey Global Institute automation benchmark:
#    60% of occupations have at least 30% technically automatable activities.
#    Source: mckinsey.com MGI "A future that works" in-brief.
# 2) U.S. BLS compliance officers median annual wage:
#    $78,420 in May 2024.
#    Source: bls.gov/ooh/business-and-financial/compliance-officers.htm
# 3) Finance formulas:
#    ROI = (Gain - Cost) / Cost, Payback period = Investment / Annual inflow.
#    Source: corporatefinanceinstitute.com resources for ROI and Payback Period.
BASE_AUTOMATION_SHARE = Decimal("0.30")
MEDIAN_COMPLIANCE_ANNUAL_WAGE = Decimal("78420")
WORK_HOURS_PER_YEAR = Decimal("2080")


class ROICalculatorService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    @staticmethod
    def _round(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _get_or_create_public_roi_org_id(self) -> UUID:
        row = self.db.execute(select(Organization).where(Organization.slug == PUBLIC_ROI_ORG_SLUG)).scalar_one_or_none()
        if row is not None:
            return row.id

        created = Organization(
            name=PUBLIC_ROI_ORG_NAME,
            slug=PUBLIC_ROI_ORG_SLUG,
            is_active=True,
            onboarding_step="completed",
            subscription_status="active",
            subscription_plan="enterprise",
        )
        self.db.add(created)
        self.db.flush()
        return created.id

    def _projected_platform_annual_cost(self, team_size: int, frameworks_count: int) -> Decimal:
        plans = self.db.execute(
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active.is_(True))
            .order_by(SubscriptionPlan.price_inr_annual.asc())
        ).scalars().all()
        if not plans:
            return Decimal("0")

        def supports(plan: SubscriptionPlan) -> bool:
            user_ok = plan.max_users is None or team_size <= int(plan.max_users)
            framework_ok = plan.max_frameworks is None or frameworks_count <= int(plan.max_frameworks)
            return user_ok and framework_ok

        selected = next((plan for plan in plans if supports(plan)), plans[-1])
        if selected.price_inr_annual is None:
            return Decimal("0")
        return Decimal(str(selected.price_inr_annual)) / Decimal("100")

    def _automation_share(self, team_size: int, frameworks_count: int) -> Decimal:
        scope_uplift = min(Decimal("0.15"), Decimal(max(frameworks_count - 1, 0)) * Decimal("0.01"))
        team_uplift = min(Decimal("0.15"), Decimal(max(team_size - 5, 0)) * Decimal("0.005"))
        return min(Decimal("0.60"), BASE_AUTOMATION_SHARE + scope_uplift + team_uplift)

    def calculate_and_capture(self, payload: ROICalculatorRequest) -> dict:
        current_annual_cost = Decimal(str(payload.current_annual_cost))
        projected_platform_annual_cost = self._projected_platform_annual_cost(payload.team_size, payload.frameworks_count)

        automation_share = self._automation_share(payload.team_size, payload.frameworks_count)
        annual_saving = current_annual_cost * automation_share

        hourly_rate = MEDIAN_COMPLIANCE_ANNUAL_WAGE / WORK_HOURS_PER_YEAR
        hours_saved_per_week = Decimal("0")
        if hourly_rate > 0:
            hours_saved_per_week = annual_saving / hourly_rate / Decimal("52")

        payback_period_months = None
        monthly_saving = annual_saving / Decimal("12")
        if monthly_saving > 0 and projected_platform_annual_cost > 0:
            payback_period_months = projected_platform_annual_cost / monthly_saving

        total_3y_benefit = annual_saving * Decimal("3")
        total_3y_cost = projected_platform_annual_cost * Decimal("3")
        if total_3y_cost > 0:
            three_year_roi_pct = ((total_3y_benefit - total_3y_cost) / total_3y_cost) * Decimal("100")
        else:
            three_year_roi_pct = Decimal("0")

        organization_id = self._get_or_create_public_roi_org_id()
        lead_summary = (
            f"Tool={payload.current_tool}; team={payload.team_size}; frameworks={payload.frameworks_count}; "
            f"annual_cost={self._round(current_annual_cost)}; annual_saving={self._round(annual_saving)}"
        )
        row = ROICalculatorLead(
            organization_id=organization_id,
            current_tool=payload.current_tool,
            team_size=payload.team_size,
            frameworks_count=payload.frameworks_count,
            current_annual_cost=self._round(current_annual_cost),
            hours_saved_per_week=self._round(hours_saved_per_week),
            annual_saving=self._round(annual_saving),
            payback_period_months=self._round(payback_period_months) if payback_period_months is not None else None,
            three_year_roi_pct=self._round(three_year_roi_pct),
            projected_platform_annual_cost=self._round(projected_platform_annual_cost),
            crm_status="new",
            lead_summary=lead_summary,
            calculation_inputs_json={
                "automation_share": str(self._round(automation_share * Decimal("100"))),
                "median_compliance_annual_wage": str(MEDIAN_COMPLIANCE_ANNUAL_WAGE),
                "work_hours_per_year": str(WORK_HOURS_PER_YEAR),
                "projected_platform_annual_cost": str(self._round(projected_platform_annual_cost)),
            },
        )
        self.db.add(row)
        self.db.flush()

        self.audit.write_audit_log(
            action="pricing.roi_lead_created",
            entity_type="roi_calculator_leads",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=None,
            after_json={
                "current_tool": row.current_tool,
                "team_size": row.team_size,
                "frameworks_count": row.frameworks_count,
                "annual_saving": float(row.annual_saving),
            },
            metadata_json={"source": "public.roi_calculator"},
        )

        return {
            "hours_saved_per_week": float(self._round(hours_saved_per_week)),
            "annual_saving": float(self._round(annual_saving)),
            "payback_period_months": float(self._round(payback_period_months)) if payback_period_months is not None else None,
            "three_year_roi_pct": float(self._round(three_year_roi_pct)),
        }
