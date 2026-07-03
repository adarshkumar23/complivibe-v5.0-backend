from __future__ import annotations

from sqlalchemy import select

from app.db.session import get_session_maker
from app.models.subscription_plan import SubscriptionPlan
from app.platform.services.billing_service import BillingService
from app.platform.services.razorpay_service import RazorpayService


def main() -> None:
    session = get_session_maker()()
    try:
        billing = BillingService(session)
        billing.ensure_default_plans()

        rzp = RazorpayService()
        plans = session.execute(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True))).scalars().all()

        for plan in plans:
            if not plan.razorpay_plan_id:
                plan.razorpay_plan_id = rzp.create_razorpay_plan(
                    plan_name=f"{plan.display_name} Monthly",
                    amount_paise=plan.price_inr_monthly,
                    interval="monthly",
                )
            if not plan.razorpay_annual_plan_id:
                plan.razorpay_annual_plan_id = rzp.create_razorpay_plan(
                    plan_name=f"{plan.display_name} Annual",
                    amount_paise=plan.price_inr_annual,
                    interval="annual",
                )

        session.commit()

        print("Razorpay plan setup complete:")
        for plan in plans:
            print(
                f"- {plan.plan_code}: monthly={plan.razorpay_plan_id} annual={plan.razorpay_annual_plan_id}"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
