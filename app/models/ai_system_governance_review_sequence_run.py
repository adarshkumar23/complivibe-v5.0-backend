import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AISystemGovernanceReviewSequenceRun(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_system_governance_review_sequence_runs"
    __table_args__ = (
        Index("ix_ai_sys_gov_seq_runs_org_pack", "organization_id", "sequence_pack_id"),
        Index("ix_ai_sys_gov_seq_runs_org_status", "organization_id", "status"),
        Index("ix_ai_sys_gov_seq_runs_org_created", "organization_id", "created_at"),
    )

    sequence_pack_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("ai_system_governance_review_sequence_packs.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    target_ai_system_ids_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    start_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    apply_constraints: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    generated_reviews_count: Mapped[int] = mapped_column(nullable=False, default=0)
    skipped_reviews_count: Mapped[int] = mapped_column(nullable=False, default=0)
    result_json: Mapped[dict | list] = mapped_column(JSON, nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
