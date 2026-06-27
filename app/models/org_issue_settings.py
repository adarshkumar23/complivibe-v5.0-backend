from sqlalchemy import Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrgIssueSettings(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "org_issue_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_org_issue_settings_organization_id"),
    )

    require_rca_before_close: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
