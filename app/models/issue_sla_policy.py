from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IssueSLAPolicy(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "issue_sla_policies"
    __table_args__ = (
        CheckConstraint("severity IN ('critical', 'high', 'medium', 'low')", name="ck_issue_sla_policies_severity"),
        UniqueConstraint("organization_id", "severity", name="uq_issue_sla_policies_org_severity"),
        Index("ix_issue_sla_policies_org_severity", "organization_id", "severity"),
    )

    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    response_sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)
