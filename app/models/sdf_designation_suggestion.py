import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class SDFDesignationSuggestion(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """A data-driven suggestion of Significant Data Fiduciary status under the DPDP Act
    2023 / DPDP Rules 2025. This is only a suggestion — a human must confirm it before
    Organization.is_significant_data_fiduciary is set. DPDP Rules 2025 (Rule 13) leaves
    exact volume/sensitivity thresholds to a separate Central Government notification
    rather than a fixed numeric rule, so this suggestion is a heuristic, not a legal
    determination."""

    __tablename__ = "sdf_designation_suggestions"
    __table_args__ = (
        Index("ix_sdf_suggestions_org_created", "organization_id", "created_at"),
    )

    suggested_sdf: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sensitive_asset_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_asset_count: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
