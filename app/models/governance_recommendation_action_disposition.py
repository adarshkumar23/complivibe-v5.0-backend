import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceRecommendationActionDisposition(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_recommendation_action_dispositions"
    __table_args__ = (
        Index(
            "ux_governance_reco_action_disp_org_snapshot_action",
            "organization_id",
            "recommendation_snapshot_id",
            "action_identity_hash",
            unique=True,
        ),
        Index("ix_governance_reco_action_disp_org_status", "organization_id", "disposition_status"),
        Index("ix_governance_reco_action_disp_org_snapshot", "organization_id", "recommendation_snapshot_id"),
        Index("ix_governance_reco_action_disp_org_action_key", "organization_id", "action_key"),
        Index("ix_governance_reco_action_disp_org_ai", "organization_id", "related_ai_system_id"),
        Index("ix_governance_reco_action_disp_org_assessment", "organization_id", "related_risk_assessment_id"),
        Index("ix_governance_reco_action_disp_org_updated", "organization_id", "updated_at"),
    )

    recommendation_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("governance_recommendation_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    action_key: Mapped[str] = mapped_column(String(128), nullable=False)
    target_entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    related_ai_system_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_risk_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_assessments.id", ondelete="SET NULL"),
        nullable=True,
    )
    disposition_status: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deferred_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
