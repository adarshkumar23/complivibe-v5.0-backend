import uuid

from sqlalchemy import ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AISystemRiskAssessmentSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_risk_assessment_snapshots"
    __table_args__ = (
        Index("ix_ai_system_risk_assessment_snapshots_org_assessment", "organization_id", "risk_assessment_id"),
        Index("ix_ai_system_risk_assessment_snapshots_org_ai_system", "organization_id", "ai_system_id"),
        Index("ix_ai_system_risk_assessment_snapshots_org_type", "organization_id", "snapshot_type"),
        Index(
            "ix_ai_system_risk_assessment_snapshots_org_assessment_version",
            "organization_id",
            "risk_assessment_id",
            "snapshot_version",
        ),
    )

    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_risk_assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_type: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(nullable=False, default=1)
    snapshot_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
