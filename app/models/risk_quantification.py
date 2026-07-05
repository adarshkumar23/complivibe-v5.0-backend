from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RiskQuantificationRun(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A single Monte Carlo / FAIR quantitative risk assessment run for a Risk.

    Methodology reference: FAIR (Factor Analysis of Information Risk) taxonomy
    per The Open Group O-RT/O-RA standards, as restated by the FAIR Institute
    (fairinstitute.org) and Freund & Jones, "Measuring and Managing Information
    Risk: A FAIR Approach" (2015).
    """

    __tablename__ = "risk_quantification_runs"
    __table_args__ = (
        CheckConstraint(
            "methodology IN ('monte_carlo', 'fair', 'fair_bayesian')",
            name="ck_risk_quantification_runs_methodology",
        ),
        CheckConstraint(
            "expected_annual_loss >= 0",
            name="ck_risk_quantification_runs_expected_annual_loss_nonneg",
        ),
        Index(
            "ix_risk_quantification_runs_org_risk_computed_at",
            "organization_id",
            "risk_id",
            "computed_at",
        ),
    )

    risk_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False
    )
    methodology: Mapped[str] = mapped_column(String(32), nullable=False)
    input_parameters_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    loss_exceedance_curve_json: Mapped[list] = mapped_column(JSON, nullable=False)
    expected_annual_loss: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    confidence_intervals_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    sensitivity_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    computed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
