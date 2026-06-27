import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataAccessLog(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_access_logs"
    __table_args__ = (
        CheckConstraint("access_type IN ('read', 'write', 'delete', 'export', 'query')", name="ck_data_access_logs_access_type"),
        CheckConstraint("access_result IN ('success', 'failed', 'partial')", name="ck_data_access_logs_access_result"),
        Index("ix_data_access_logs_org_asset_time", "organization_id", "data_asset_id", "access_time"),
        Index("ix_data_access_logs_org_actor_time", "organization_id", "actor_id", "access_time"),
        Index("ix_data_access_logs_org_result", "organization_id", "access_result"),
        Index("ix_data_access_logs_access_time", "access_time"),
        Index("ix_data_access_logs_source_country", "source_country"),
    )

    data_asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_external: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_type: Mapped[str] = mapped_column(String(20), nullable=False)
    access_result: Mapped[str] = mapped_column(String(10), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    source_country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    bytes_transferred: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
