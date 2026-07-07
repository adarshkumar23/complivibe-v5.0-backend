import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RootCauseAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "root_cause_analyses"
    __table_args__ = (
        Index("ix_root_cause_analyses_org_issue", "organization_id", "issue_id"),
        Index("ix_root_cause_analyses_org_authored", "organization_id", "authored_by"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, unique=True)
    # Snapshot of the issue's severity at the moment this RCA was authored.
    # If the issue's severity is later changed (e.g. a re-triage), the RCA's
    # findings/timeline may no longer reflect the actual blast radius --
    # RCARead compares this against the issue's current severity to flag that
    # explicitly instead of silently presenting stale analysis as current.
    severity_at_creation: Mapped[str | None] = mapped_column(String(20), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    timeline_description: Mapped[str] = mapped_column(Text, nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_factors: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    corrective_actions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    preventive_measures: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    authored_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
