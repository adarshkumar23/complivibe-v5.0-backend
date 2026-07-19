import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GovernanceGraphNode(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A node in the P2 governance knowledge-graph (patent P2).

    Nodes are regulatory-structure concepts (regulation, jurisdiction,
    data_category, risk_tier, obligation, control_type) plus ai_system anchors.
    ai_system nodes are keyed by ``node_key == str(ai_system_id)``. The optional
    384-dim ``embedding`` supports semantic similarity (HNSW index defined in
    the migration); it is nullable and not required for graph traversal.
    """

    __tablename__ = "governance_graph_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('ai_system', 'control_type', 'data_category', 'jurisdiction', "
            "'obligation', 'regulation', 'risk_tier')",
            name="ck_governance_graph_nodes_node_type",
        ),
        UniqueConstraint("organization_id", "node_type", "node_key", name="uq_governance_graph_nodes_org_type_key"),
        Index("ix_governance_graph_nodes_org_node_type", "organization_id", "node_type"),
    )

    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    node_key: Mapped[str] = mapped_column(String(255), nullable=False)
    properties: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
