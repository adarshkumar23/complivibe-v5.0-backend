import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Numeric, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EntityRiskScore(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "entity_risk_scores"
    __table_args__ = (
        Index("ix_entity_risk_scores_org_type_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_entity_risk_scores_org_type_computed", "organization_id", "entity_type", "computed_at"),
        Index("ix_entity_risk_scores_org_band", "organization_id", "score_band"),
    )

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entity_label: Mapped[str] = mapped_column(String(255), nullable=False)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    score_band: Mapped[str] = mapped_column(String(20), nullable=False)
    risk_count: Mapped[int] = mapped_column(nullable=False)
    score_method: Mapped[str] = mapped_column(String(30), nullable=False, default="equal_weight")
    component_risks_json: Mapped[list[dict] | dict] = mapped_column(JSON, nullable=False, default=list)
    computation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
