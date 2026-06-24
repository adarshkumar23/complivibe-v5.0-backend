import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AISystemGovernancePolicyResolutionSimulationReport(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_policy_resolution_simulation_reports"
    __table_args__ = (
        Index("ix_ai_sys_gov_policy_res_sim_reports_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_policy_res_sim_reports_org_created", "organization_id", "created_at"),
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="generated")
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_contexts_json: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    result_json: Mapped[list | dict] = mapped_column(JSON, nullable=False)
    context_count: Mapped[int] = mapped_column(nullable=False, default=0)
    blocked_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    warning_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    no_policy_contexts_count: Mapped[int] = mapped_column(nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
