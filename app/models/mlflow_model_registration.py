import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class MLflowModelRegistration(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "mlflow_model_registrations"
    __table_args__ = (
        Index("ix_mf_reg_org_model", "organization_id", "model_name"),
        Index("ix_mf_reg_org_comp", "organization_id", "compliance_status"),
        Index("ix_mf_reg_ai_sys", "ai_system_id"),
        Index("ix_mf_reg_conn", "mlflow_connection_id"),
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
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metrics_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    tags_json: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    compliance_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending_review")
    auto_linked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_risk_created: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_risk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("risks.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
