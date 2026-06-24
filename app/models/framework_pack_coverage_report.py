import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class FrameworkPackCoverageReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "framework_pack_coverage_reports"
    __table_args__ = (
        Index("ix_framework_pack_cov_framework", "framework_id"),
        Index("ix_framework_pack_cov_framework_version", "framework_version_id"),
        Index("ix_framework_pack_cov_pack_key", "pack_key"),
        Index("ix_framework_pack_cov_generated_at", "generated_at"),
    )

    framework_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("frameworks.id", ondelete="CASCADE"), nullable=False)
    framework_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("framework_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    pack_key: Mapped[str] = mapped_column(String(128), nullable=False)
    coverage_level: Mapped[str] = mapped_column(String(32), nullable=False, default="starter")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    total_sections: Mapped[int] = mapped_column(nullable=False, default=0)
    total_obligations: Mapped[int] = mapped_column(nullable=False, default=0)
    obligations_with_content: Mapped[int] = mapped_column(nullable=False, default=0)
    obligations_with_questions: Mapped[int] = mapped_column(nullable=False, default=0)
    obligations_with_evidence_requirements: Mapped[int] = mapped_column(nullable=False, default=0)
    obligations_with_control_suggestions: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_content_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_question_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_evidence_requirement_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_control_suggestion_count: Mapped[int] = mapped_column(nullable=False, default=0)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
