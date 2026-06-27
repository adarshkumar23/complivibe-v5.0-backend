import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class DataAccessAnomalyRule(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "data_access_anomaly_rules"
    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('access_count_spike', 'after_hours_access', 'new_actor_access', 'mass_download', 'failed_access_spike', 'cross_border_access', 'sensitivity_mismatch_access')",
            name="ck_data_access_anomaly_rules_rule_type",
        ),
        Index("ix_data_access_anomaly_rules_org_type_active", "organization_id", "rule_type", "is_active"),
        Index("ix_data_access_anomaly_rules_org_asset_active", "organization_id", "data_asset_id", "is_active"),
    )

    data_asset_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("data_assets.id", ondelete="CASCADE"), nullable=True)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    rule_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
