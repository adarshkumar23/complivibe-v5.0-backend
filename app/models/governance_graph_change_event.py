import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class GovernanceGraphChangeEvent(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    """Outbox row for the hybrid-trigger change path (patent P2).

    When a watched AI-system field changes (or a manual sync fires), a row is
    written here; the satellite's export endpoints filter ``changed_since``
    against it to pull only affected systems. ``consumed_at`` marks drain.
    """

    __tablename__ = "governance_graph_change_events"
    __table_args__ = (
        Index("ix_ggce_org_ai_system", "organization_id", "ai_system_id"),
        Index("ix_ggce_changed_at", "changed_at"),
    )

    ai_system_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_systems.id", ondelete="CASCADE"), nullable=False
    )
    changed_field: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
