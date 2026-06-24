import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class TechnicalControlResult(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "technical_control_results"
    __table_args__ = (
        Index("ix_technical_control_results_org_rule_created", "organization_id", "rule_id", "created_at"),
        Index("ix_technical_control_results_org_agent_created", "organization_id", "agent_id", "created_at"),
        Index("ix_technical_control_results_org_passed_created", "organization_id", "passed", "created_at"),
    )

    rule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("technical_control_rules.id", ondelete="RESTRICT"),
        nullable=False,
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("technical_control_agents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    resource_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actual_config_key: Mapped[str] = mapped_column(String(255), nullable=False)
    actual_config_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_test_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("control_test_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
