import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class PolicyRiskMapping(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_risk_mappings"
    __table_args__ = (
        CheckConstraint(
            "mitigation_strength IN ('full', 'partial', 'indirect')",
            name="ck_policy_risk_mappings_mitigation_strength",
        ),
        Index("ix_policy_risk_mappings_org_policy", "organization_id", "policy_id"),
        Index("ix_policy_risk_mappings_org_risk", "organization_id", "risk_id"),
        Index("ix_policy_risk_mappings_org_deleted_at", "organization_id", "deleted_at"),
        Index(
            "uq_policy_risk_mappings_policy_risk_active",
            "policy_id",
            "risk_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("compliance_policies.id", ondelete="CASCADE"), nullable=False)
    risk_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("risks.id", ondelete="CASCADE"), nullable=False)
    mitigation_strength: Mapped[str] = mapped_column(String(20), nullable=False, default="partial")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapped_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
