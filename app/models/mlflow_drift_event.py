import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class MLflowDriftEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "mlflow_drift_events"
    __table_args__ = (
        Index("ix_mf_drift_org_sev", "organization_id", "severity"),
        Index("ix_mf_drift_org_model", "organization_id", "model_name"),
        Index("ix_mf_drift_ai_sys", "ai_system_id"),
    )

    mlflow_connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("mlflow_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="SET NULL"),
        nullable=True,
    )
    mlflow_model_registration_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("mlflow_model_registrations.id", ondelete="SET NULL"),
        nullable=True,
    )
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    drift_metric: Mapped[str] = mapped_column(String(150), nullable=False)
    drift_value: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    drift_threshold: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    drift_context_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    auto_risk_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
