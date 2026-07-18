import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class AiDerivedGuardrail(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A compiled, tenant-scoped guardrail DERIVED from one or more regulatory
    obligations (patent P3).

    Distinct from the human-authored `ai_policy_guardrails` table (migration
    0128): that stores a manually-defined constraint + monitoring events; this
    stores obligation-derived, Rego-compiled, allow/deny-enforcement policy with
    per-obligation provenance.

    `source_obligation_ids` and `constraint_spec_json` together are the
    provenance record (patent Claim 1): they let a guardrail's Rego be traced
    back to the obligation text that produced it, so that when an obligation is
    amended upstream, affected guardrails can be identified and recompiled.
    """

    __tablename__ = "ai_derived_guardrails"
    __table_args__ = (
        Index(
            "ix_ai_derived_guardrails_org_system_active",
            "organization_id",
            "ai_system_id",
            "is_active",
        ),
        Index("ix_ai_derived_guardrails_org_active", "organization_id", "is_active"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rego_policy: Mapped[str] = mapped_column(Text, nullable=False)
    rego_package: Mapped[str] = mapped_column(String(255), nullable=False)
    # Provenance fields (patent Claim 1). Do not remove without an equivalent
    # replacement -- a schema that only stores the compiled Rego would not
    # support the provenance claim.
    source_obligation_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    constraint_spec_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    compiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
