"""AI-assist assessment of uploaded evidence — an isolated, read-only-over-the-
rest-of-the-system sink.

Two tables, the ONLY tables this feature ever writes:
  * ``evidence_ai_assessment_candidates`` — the lightweight flag queue the Phase 1
    event bus writes into (flush-only, on EVIDENCE_UPLOADED) so the APScheduler
    drain can do extraction + the AI call OUTSIDE the publisher's transaction.
  * ``evidence_ai_assessments`` — the persisted, org-scoped assessment.

The assessment is a SUGGESTION with reasoning, never a verdict: status is one of
suggested_valid / suggested_incomplete / suggested_mismatch / unable_to_assess.
It NEVER writes to evidence_items (in particular never touches review_status,
which stays the human reviewer's field) or any other existing table.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin

# The only allowed assessment statuses. Deliberately NO "valid"/"verified"/
# "correct" boolean -- the AI assesses, it does not certify.
ASSESSMENT_STATUSES = ("suggested_valid", "suggested_incomplete", "suggested_mismatch", "unable_to_assess")
CONTENT_SOURCES = ("r2_file", "external_url", "none")


class EvidenceAiAssessment(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_ai_assessments"
    __table_args__ = (
        CheckConstraint(
            "ai_assessment_status IN ('suggested_valid', 'suggested_incomplete', "
            "'suggested_mismatch', 'unable_to_assess')",
            name="ck_evidence_ai_assessments_status",
        ),
        Index("ix_evidence_ai_assessments_org_evidence", "organization_id", "evidence_item_id", "created_at"),
    )

    evidence_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False
    )
    ai_assessment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    appears_to_be: Mapped[str | None] = mapped_column(Text, nullable=True)
    appears_to_cover: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_or_mismatched_json: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    # Context provenance (snapshot of what the assessment was reasoned against).
    linked_control_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    content_source: Mapped[str] = mapped_column(String(32), nullable=False, default="none")
    extracted_text_chars: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    provider_used: Mapped[str | None] = mapped_column(String(20), nullable=True)
    used_byo_credentials: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    assessment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EvidenceAiAssessmentCandidate(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A newly-uploaded evidence item flagged (flush-only) for AI assessment.

    Written by the event-bus listener inside the publisher's transaction; the
    drain processes unprocessed rows in its OWN committed session.
    """

    __tablename__ = "evidence_ai_assessment_candidates"
    __table_args__ = (
        Index("ix_evidence_ai_assessment_candidates_pending", "organization_id", "processed_at"),
    )

    evidence_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    flagged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
