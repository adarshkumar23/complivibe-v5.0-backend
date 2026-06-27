import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class IncidentClassification(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "incident_classifications"
    __table_args__ = (
        CheckConstraint(
            "category IN ('security_breach', 'privacy_violation', 'service_disruption', 'data_corruption', 'unauthorized_access', 'insider_threat', 'third_party_failure', 'regulatory_event')",
            name="ck_incident_classifications_category",
        ),
        UniqueConstraint("issue_id", name="uq_incident_classifications_issue_id"),
        Index("ix_incident_classifications_org_category", "organization_id", "category"),
        Index("ix_incident_classifications_org_issue", "organization_id", "issue_id"),
    )

    issue_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regulatory_implications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notification_required: Mapped[bool] = mapped_column(nullable=False, default=False)
    auto_classified: Mapped[bool] = mapped_column(nullable=False, default=True)
    classification_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
