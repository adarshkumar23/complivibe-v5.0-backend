import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, UUIDPrimaryKeyMixin


class PAMSessionRecord(UUIDPrimaryKeyMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "pam_session_records"
    __table_args__ = (
        Index("ix_pam_session_records_org_started", "organization_id", "started_at"),
        Index("ix_pam_session_records_org_approval", "organization_id", "approval_status"),
        Index("ix_pam_session_records_org_risk", "organization_id", "risk_status"),
        Index("ix_pam_session_records_org_identity_target", "organization_id", "identity", "target_system"),
        Index("uq_pam_session_records_org_external", "organization_id", "external_session_id", unique=True),
    )

    external_session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    pam_provider: Mapped[str | None] = mapped_column(String(120), nullable=True)
    identity: Mapped[str] = mapped_column(String(255), nullable=False)
    privileged_account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_system: Mapped[str] = mapped_column(String(255), nullable=False)
    target_resource_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approval_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    risk_status: Mapped[str] = mapped_column(String(40), nullable=False, default="monitor")
    risk_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="api_key_ingest")
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    flagged_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    flagged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
