import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class MLflowConnection(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "mlflow_connections"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_mf_conn_org"),)

    connection_name: Mapped[str] = mapped_column(String(150), nullable=False)
    ingest_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tracking_server_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
