import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class ApplicabilityEvaluationResult(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "applicability_evaluation_results"
    __table_args__ = (
        Index("ix_app_eval_results_org_run", "organization_id", "evaluation_run_id"),
        Index("ix_app_eval_results_org_obligation", "organization_id", "obligation_id"),
    )

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("applicability_evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    obligation_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("obligations.id", ondelete="CASCADE"), nullable=False)
    suggested_applicability: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_applicability: Mapped[str | None] = mapped_column(String(32), nullable=True)
    state_updated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matched_rules_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    missing_answers_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
