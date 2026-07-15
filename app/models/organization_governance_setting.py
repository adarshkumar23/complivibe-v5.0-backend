import uuid

from sqlalchemy import Boolean, ForeignKey, Index, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationGovernanceSetting(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "organization_governance_settings"
    __table_args__ = (
        Index(
            "ix_organization_governance_settings_org",
            "organization_id",
            unique=True,
        ),
    )

    batch_cancellation_requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    batch_cancellation_policy_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    autopilot_auto_execute_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    autopilot_auto_execute_confidence_threshold: Mapped[float] = mapped_column(nullable=False, default=0.95)
    autopilot_auto_execute_reversal_window_hours: Mapped[int] = mapped_column(nullable=False, default=24)
    # Phase 5 independent kill-switch: enables ONLY cross-domain graph-aware
    # candidate generation, default OFF, without touching base Autopilot.
    autopilot_graph_reasoning_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
