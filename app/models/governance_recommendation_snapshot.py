import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class GovernanceRecommendationSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "governance_recommendation_snapshots"
    __table_args__ = (
        Index("ix_governance_recommendation_snapshots_org_scope", "organization_id", "scope_type", "scope_id"),
        Index("ix_governance_recommendation_snapshots_org_created", "organization_id", "created_at"),
        Index("ix_governance_recommendation_snapshots_org_source", "organization_id", "source_type"),
        Index("ix_governance_recommendation_snapshots_org_version", "organization_id", "scope_type", "scope_id", "snapshot_version"),
    )

    scope_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="candidate_actions")
    candidate_count: Mapped[int] = mapped_column(nullable=False, default=0)
    recommendation_payload_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    source_signal_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    source_candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(nullable=False, default=1)
    previous_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("governance_recommendation_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    diff_from_previous_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
