import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ScoreSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "score_snapshots"
    __table_args__ = (
        Index("ix_score_snapshots_org_created", "organization_id", "created_at"),
        Index("ix_score_snapshots_org_type_calc", "organization_id", "snapshot_type", "calculated_at"),
    )

    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False, default="compliance_readiness")
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[str] = mapped_column(String(8), nullable=False, default="F")
    inputs_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    breakdown_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommendations_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
