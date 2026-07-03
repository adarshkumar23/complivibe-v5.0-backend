import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin

# Native Postgres ENUM types created explicitly in migration 0093 (grandfathered
# exception to the no-native-ENUM rule). create_type=False because the migration
# owns CREATE TYPE/DROP TYPE; sa.Enum falls back to a CHECK-constrained VARCHAR
# on sqlite, so this stays cross-dialect for tests.
_scope_type_enum = Enum(
    "org", "business_unit", name="risk_appetite_scope_type_enum", create_type=False
)
_risk_category_enum = Enum(
    "operational",
    "financial",
    "compliance",
    "reputational",
    "technology",
    "vendor",
    name="risk_appetite_category_enum",
    create_type=False,
)


class RiskAppetiteThreshold(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "risk_appetite_thresholds"
    __table_args__ = (
        Index("ix_risk_appetite_thresholds_org_active", "organization_id", "is_active"),
        Index("ix_risk_appetite_thresholds_org_category", "organization_id", "risk_category"),
        Index("ix_risk_appetite_thresholds_org_scope", "organization_id", "scope_type", "scope_id"),
    )

    scope_type: Mapped[str] = mapped_column(_scope_type_enum, nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    risk_category: Mapped[str] = mapped_column(_risk_category_enum, nullable=False)
    max_acceptable_score: Mapped[int] = mapped_column(Integer, nullable=False)
    escalation_owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
