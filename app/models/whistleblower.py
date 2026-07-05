import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class WhistleblowerReport(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """A whistleblower hotline report.

    CRITICAL ANONYMITY INVARIANT: this table must NEVER contain any column that
    could identify the reporter. There is intentionally no created_by/submitter
    user FK, no IP address column, and no session reference. The only credential
    a reporter holds is a high-entropy tracking code, which is stored here ONLY
    as a salted-by-design sha256 hash (`tracking_code_hash`) -- the raw code is
    never persisted anywhere. `anonymous_id` is a separate opaque, non-secret
    reference token (not a hash) that may be surfaced back to the reporter for
    display purposes; it carries no identity information either.
    """

    __tablename__ = "whistleblower_reports"
    __table_args__ = (
        CheckConstraint(
            "category IN ('fraud', 'corruption', 'harassment', 'safety_violation', 'data_privacy', "
            "'financial_misconduct', 'discrimination', 'retaliation', 'other')",
            name="ck_whistleblower_reports_category",
        ),
        CheckConstraint(
            "status IN ('submitted', 'under_review', 'investigating', 'resolved', 'closed', 'dismissed')",
            name="ck_whistleblower_reports_status",
        ),
        Index("ix_whistleblower_reports_org_status", "organization_id", "status"),
    )

    anonymous_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    tracking_code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="submitted")
    assigned_investigator_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class WhistleblowerMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A message in a whistleblower report's thread.

    When sender_type == 'reporter', sender_user_id MUST be null -- reporters are
    never linked to a real user account. When sender_type == 'investigator',
    sender_user_id is the real staff member's id (investigators are not anonymous).
    """

    __tablename__ = "whistleblower_messages"
    __table_args__ = (
        CheckConstraint(
            "sender_type IN ('reporter', 'investigator')",
            name="ck_whistleblower_messages_sender_type",
        ),
        Index("ix_whistleblower_messages_report_created", "report_id", "created_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("whistleblower_reports.id", ondelete="CASCADE"), nullable=False
    )
    sender_type: Mapped[str] = mapped_column(String(20), nullable=False)
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
