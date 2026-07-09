import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_significant_data_fiduciary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sdf_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dpdp_registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    consent_manager_registered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    subscription_status: Mapped[str] = mapped_column(String(20), nullable=False, default="trial")
    subscription_plan: Mapped[str] = mapped_column(String(20), nullable=False, default="starter")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    subscription_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    razorpay_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    usage_spend_cap_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    usage_spend_cap_inr: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    sanctions_match_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.8500"))
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_step: Mapped[str | None] = mapped_column(String(30), nullable=True, default="not_started")
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Shared secret used to verify the HMAC-SHA256 signature on inbound
    # compliance-bot Slack/Teams webhook requests -- see
    # ComplianceBotService.verify_webhook_signature. Signature-only auth, same
    # pattern as issue-sync connections' webhook_secret and the Razorpay webhook.
    compliance_bot_webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
