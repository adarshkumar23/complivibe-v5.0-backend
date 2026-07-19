import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GovernanceGraphEdge(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A directed, weighted edge between two governance-graph nodes (patent P2).

    ``edge_type`` is constrained to the known regulatory-relation vocabulary
    (see governance_graph.constants.EDGE_TYPES); the manual-edge endpoint
    validates against the same set and rejects unknown types with HTTP 422.
    """

    __tablename__ = "governance_graph_edges"
    __table_args__ = (
        CheckConstraint(
            "edge_type IN ('data_triggers', 'jurisdiction_has', 'obligation_needs', "
            "'regulation_requires', 'risk_tier_adds', 'system_classified_as', "
            "'system_deploys_in', 'system_uses')",
            name="ck_governance_graph_edges_edge_type",
        ),
        Index("ix_governance_graph_edges_org_source", "organization_id", "source_node_id"),
        Index("ix_governance_graph_edges_org_edge_type", "organization_id", "edge_type"),
    )

    source_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("governance_graph_nodes.id", ondelete="CASCADE"), nullable=False
    )
    target_node_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("governance_graph_nodes.id", ondelete="CASCADE"), nullable=False
    )
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
