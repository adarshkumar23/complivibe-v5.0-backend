import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DataPrincipalNomination(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """DPDP Act 2023 Section 10 (DPDP Rules 2025, Rule 10): a Data Principal may nominate
    another individual to exercise their rights in the event of death or incapacity."""

    __tablename__ = "data_principal_nominations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked', 'activated')", name="ck_dp_nominations_status"),
        CheckConstraint("activation_trigger IN ('death', 'incapacity')", name="ck_dp_nominations_activation_trigger"),
        CheckConstraint(
            "nominee_user_id IS NOT NULL OR nominee_name IS NOT NULL",
            name="ck_dp_nominations_nominee_identified",
        ),
        Index("ix_dp_nominations_org_subject_status", "organization_id", "subject_identifier_hash", "status"),
    )

    subject_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nominee_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    nominee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nominee_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activation_trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
