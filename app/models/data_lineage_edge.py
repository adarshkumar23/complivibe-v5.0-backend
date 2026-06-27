import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataLineageEdge(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_lineage_edges"
    __table_args__ = (
        CheckConstraint(
            "source_method IN ('manual', 'openlineage_event', 'openmetadata_sync')",
            name="ck_data_lineage_edges_source_method",
        ),
        UniqueConstraint(
            "organization_id",
            "upstream_node_id",
            "downstream_node_id",
            "pipeline_name",
            name="uq_data_lineage_edges_org_up_down_pipeline",
        ),
        Index("ix_data_lineage_edges_org_upstream", "organization_id", "upstream_node_id"),
        Index("ix_data_lineage_edges_org_downstream", "organization_id", "downstream_node_id"),
        Index("ix_data_lineage_edges_org_source_method", "organization_id", "source_method"),
        Index("ix_data_lineage_edges_event_time", "event_time"),
    )

    upstream_node_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_lineage_nodes.id", ondelete="CASCADE"), nullable=False)
    downstream_node_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_lineage_nodes.id", ondelete="CASCADE"), nullable=False)
    transformation_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_method: Mapped[str] = mapped_column(String(30), nullable=False)
    pipeline_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pipeline_run_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
