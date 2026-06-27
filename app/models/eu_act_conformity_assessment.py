import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class EUActConformityAssessment(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "eu_act_conformity_assessments"
    __table_args__ = (
        CheckConstraint(
            "assessment_type IN ('self_assessment', 'notified_body')",
            name="ck_eu_act_conformity_assessments_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'in_progress', 'complete', 'submitted')",
            name="ck_eu_act_conformity_assessments_status",
        ),
        Index("ix_eu_act_conformity_assessments_org_system", "organization_id", "ai_system_id"),
        Index("ix_eu_act_conformity_assessments_org_status", "organization_id", "status"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False)
    assessment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    technical_documentation_complete: Mapped[bool] = mapped_column(nullable=False, default=False)
    qms_compliant: Mapped[bool] = mapped_column(nullable=False, default=False)
    human_oversight_measures: Mapped[str | None] = mapped_column(Text, nullable=True)
    accuracy_robustness_measures: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist_items: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
