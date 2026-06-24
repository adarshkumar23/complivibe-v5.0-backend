import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class PolicyTemplateClone(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "policy_template_clones"
    __table_args__ = (
        Index("ix_policy_template_clones_org_template", "organization_id", "template_id"),
        Index("ix_policy_template_clones_org_policy", "organization_id", "cloned_policy_id"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("policy_templates.id", ondelete="RESTRICT"), nullable=False)
    cloned_policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("compliance_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    cloned_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    cloned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    customization_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
