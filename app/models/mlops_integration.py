import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class MLOpsIntegration(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "mlops_integrations"
    __table_args__ = (
        CheckConstraint(
            "integration_type IN ('mlflow', 'databricks', 'sagemaker', 'vertex_ai')",
            name="ck_mlops_integrations_type",
        ),
        CheckConstraint(
            "sync_status IS NULL OR sync_status IN ('success', 'failed', 'in_progress')",
            name="ck_mlops_integrations_sync_status",
        ),
        Index("ix_mlops_integrations_org_type", "organization_id", "integration_type"),
        Index("ix_mlops_integrations_org_active", "organization_id", "is_active"),
    )

    integration_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
