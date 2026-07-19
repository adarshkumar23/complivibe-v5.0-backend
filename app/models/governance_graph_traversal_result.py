import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GovernanceGraphTraversalResult(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A persisted obligation-derivation result for one AI system (patent P2).

    Records what was derived (obligations/controls), the graph path, the
    methodology version, why it ran (``trigger_reason``), and the outcome of
    core's independent re-validation (``validation_status``: validated /
    flagged_mismatch / self_derived).
    """

    __tablename__ = "governance_graph_traversal_results"
    __table_args__ = (
        CheckConstraint(
            "trigger_reason IN ('event', 'on_demand', 'scheduled')",
            name="ck_ggtr_trigger_reason",
        ),
        CheckConstraint(
            "validation_status IN ('flagged_mismatch', 'self_derived', 'validated')",
            name="ck_ggtr_validation_status",
        ),
        Index("ix_ggtr_org_ai_system", "organization_id", "ai_system_id"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False
    )
    traversal_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    input_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    derived_obligations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    derived_controls: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    graph_path: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    methodology_version: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_reason: Mapped[str] = mapped_column(String(16), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False)
