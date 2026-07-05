import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CrisisPlaybook(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "crisis_playbooks"
    __table_args__ = (
        CheckConstraint(
            "scenario_type IN ("
            "'cyber_incident', 'natural_disaster', 'pandemic', 'financial_crisis', "
            "'supply_chain_disruption', 'data_breach', 'regulatory_action', "
            "'reputational_crisis', 'other')",
            name="ck_crisis_playbooks_scenario_type",
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'draft')",
            name="ck_crisis_playbooks_status",
        ),
        Index("ix_crisis_playbooks_org_scenario_type", "organization_id", "scenario_type"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scenario_type: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_conditions_json: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    steps_json: Mapped[list] = mapped_column(JSON, nullable=False)
    owner_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class CrisisActivation(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "crisis_activations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'resolved', 'cancelled')",
            name="ck_crisis_activations_status",
        ),
        Index("ix_crisis_activations_org_status", "organization_id", "status"),
    )

    playbook_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("crisis_playbooks.id", ondelete="CASCADE"), nullable=False
    )
    activated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    linked_processes_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    linked_risks_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
