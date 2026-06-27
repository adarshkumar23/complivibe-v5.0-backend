import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataLineageNode(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_lineage_nodes"
    __table_args__ = (
        CheckConstraint(
            "node_type IN ('data_asset', 'transform', 'external_source', 'external_destination', 'api_endpoint', 'pipeline_step')",
            name="ck_data_lineage_nodes_node_type",
        ),
        UniqueConstraint("organization_id", "name", "system_name", name="uq_data_lineage_nodes_org_name_system"),
        Index("ix_data_lineage_nodes_org_node_type", "organization_id", "node_type"),
        Index("ix_data_lineage_nodes_org_data_asset", "organization_id", "data_asset_id"),
    )

    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    data_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
