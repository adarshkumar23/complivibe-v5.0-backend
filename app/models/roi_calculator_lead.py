import uuid

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ROICalculatorLead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roi_calculator_leads"
    __table_args__ = (
        Index("ix_roi_calculator_leads_org_created_at", "organization_id", "created_at"),
        Index("ix_roi_calculator_leads_current_tool", "current_tool"),
        Index("ix_roi_calculator_leads_crm_status", "crm_status"),
        CheckConstraint(
            "current_tool IN ('vanta','drata','sprinto','scrut','onetrust','credo_ai','generic','other')",
            name="ck_roi_calculator_leads_current_tool",
        ),
        CheckConstraint("team_size >= 1", name="ck_roi_calculator_leads_team_size"),
        CheckConstraint("frameworks_count >= 1", name="ck_roi_calculator_leads_frameworks_count"),
        CheckConstraint("current_annual_cost >= 0", name="ck_roi_calculator_leads_current_annual_cost"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    current_tool: Mapped[str] = mapped_column(String(32), nullable=False)
    team_size: Mapped[int] = mapped_column(nullable=False)
    frameworks_count: Mapped[int] = mapped_column(nullable=False)
    current_annual_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    hours_saved_per_week: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    annual_saving: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    payback_period_months: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    three_year_roi_pct: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    projected_platform_annual_cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    crm_status: Mapped[str] = mapped_column(String(24), nullable=False, default="new")
    lead_summary: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_inputs_json: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict)
