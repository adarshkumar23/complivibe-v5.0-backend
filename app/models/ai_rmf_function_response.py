import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class AIRMFFunctionResponse(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "ai_rmf_function_responses"
    __table_args__ = (
        CheckConstraint(
            "function IN ('govern', 'map', 'measure', 'manage')",
            name="ck_ai_rmf_function_responses_function",
        ),
        CheckConstraint(
            "response_status IN ('not_addressed', 'partial', 'implemented')",
            name="ck_ai_rmf_function_responses_status",
        ),
        UniqueConstraint("implementation_id", "subcategory_ref", name="uq_ai_rmf_function_responses_impl_subcategory"),
        Index("ix_ai_rmf_function_responses_impl_function", "implementation_id", "function"),
        Index("ix_ai_rmf_function_responses_org_impl", "organization_id", "implementation_id"),
    )

    implementation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("nist_ai_rmf_implementations.id", ondelete="CASCADE"),
        nullable=False,
    )
    function: Mapped[str] = mapped_column(String(20), nullable=False)
    subcategory_ref: Mapped[str] = mapped_column(String(30), nullable=False)
    response_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_addressed")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
