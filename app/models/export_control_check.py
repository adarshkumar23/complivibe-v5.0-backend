import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import OrganizationOwnedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExportControlCheck(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    """Export control compliance screening result for a vendor transaction/item (T4-8).

    Grounded in:
      - ECCN (Export Control Classification Number): a 5-character
        alphanumeric code (e.g. "4A001") under the US Commerce Control List
        (CCL), administered by BIS. Items not on the CCL default to EAR99
        (no specific ECCN, generally low control but not license-free in
        all cases).
      - Denied/restricted-party lists: BIS Denied Persons List, BIS Entity
        List, BIS Unverified List, OFAC SDN List, State Dept AECA Debarred
        List.
      - Free public consolidated dataset: trade.gov Consolidated Screening
        List (CSL), https://www.trade.gov/consolidated-screening-list --
        merges BIS Denied Persons/Entity/Unverified Lists, OFAC SDN, and
        State Dept AECA Debarred List into one free, public dataset.
      - License determination is a function of (1) the ECCN's Reason(s)
        for Control, (2) destination country cross-referenced against the
        Commerce Country Chart (EAR Supp. 1 to Part 738), OR (3) a
        positive denied-party screening match. See
        app/satellites/tprm_intelligence/export_control_screening.py for
        the full computation.

    IMPORTANT: `license_required`/`license_determination_basis` are an
    INITIAL SCREENING SIGNAL requiring human/legal confirmation, NOT a
    final legal export-control determination.
    """

    __tablename__ = "export_control_checks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('screened', 'license_pending', 'cleared', 'blocked')",
            name="ck_export_control_checks_status",
        ),
        Index("ix_export_control_checks_org_vendor_computed", "organization_id", "vendor_id", "computed_at"),
    )

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False)
    item_description: Mapped[str] = mapped_column(String(500), nullable=False)
    eccn: Mapped[str | None] = mapped_column(String(10), nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    destination_country: Mapped[str] = mapped_column(String(100), nullable=False)
    denied_party_screening_result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    license_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    license_determination_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="screened")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    computed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
