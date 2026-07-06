import uuid

from datetime import datetime

from sqlalchemy import BIGINT, JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceItem(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "evidence_items"
    __table_args__ = (
        Index("ix_evidence_org_review_status", "organization_id", "review_status"),
        Index("ix_evidence_org_freshness_status", "organization_id", "freshness_status"),
        Index("ix_evidence_org_type", "organization_id", "evidence_type"),
        Index("ix_evidence_org_source", "organization_id", "source"),
    )

    # Kept as mapped to existing column name for backward migration compatibility.
    title: Mapped[str] = mapped_column("name", String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="other")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    source_import_tool: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_reviewed")
    freshness_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_reference_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Kept mapped to existing column name for backward migration compatibility.
    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        "uploaded_by", Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    legacy_control_id: Mapped[uuid.UUID | None] = mapped_column(
        "control_id", Uuid, ForeignKey("controls.id", ondelete="SET NULL"), nullable=True
    )
