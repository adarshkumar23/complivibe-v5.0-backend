import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class CloudFindingControlMappingRule(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Rule-based finding-category -> control mapping. Matches
    ControlRecommendationService's existing confidence vocabulary
    (deterministic_exact/deterministic_partial/needs_review) so both suggestion families
    read the same way to a human reviewer."""

    __tablename__ = "cloud_finding_control_mapping_rules"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ('deterministic_exact', 'deterministic_partial', 'needs_review')",
            name="ck_cloud_finding_mapping_rules_confidence",
        ),
        Index("ix_cloud_finding_mapping_rules_org_category", "organization_id", "finding_category"),
    )

    finding_category: Mapped[str] = mapped_column(String(100), nullable=False)
    target_control_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=True)
    target_control_common_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic_partial")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class FindingControlSuggestion(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A candidate finding->control link awaiting human confirmation (or already
    auto-applied for deterministic_exact matches when the connector opts in)."""

    __tablename__ = "finding_control_suggestions"
    __table_args__ = (
        CheckConstraint(
            "confidence IN ('deterministic_exact', 'deterministic_partial', 'needs_review')",
            name="ck_finding_control_suggestions_confidence",
        ),
        CheckConstraint("status IN ('open', 'applied', 'dismissed')", name="ck_finding_control_suggestions_status"),
        Index("ix_finding_control_suggestions_org_status", "organization_id", "status"),
    )

    connector_event_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cloud_evidence_connector_events.id", ondelete="CASCADE"), nullable=False
    )
    evidence_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_items.id", ondelete="CASCADE"), nullable=False)
    suggested_control_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("controls.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    applied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
