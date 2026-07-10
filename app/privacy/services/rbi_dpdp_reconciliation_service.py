"""RBI-DPDP reconciliation engine.

Core tension: RBI/PMLA minimum-retention obligations vs. DPDP Act 2023 purpose-limitation
and erasure (Section 12). Confirmed via web research (see build report for full citations):
the RBI Master Direction on KYC (2016, as amended) requires retaining KYC/identity records
for five years after the end of the customer relationship; the Prevention of Money
Laundering Act, 2002 (read with the PML (Maintenance of Records) Rules, 2005) similarly
requires five years' retention of transaction records. DPDP Act 2023 Section 8(5)/Section
12 explicitly permits retention beyond the DPDP purpose-limitation default where another
law requires it — so the RBI/PMLA retention floor governs until it lapses; DPDP erasure
only becomes available once that floor has passed. This is a live compliance question
in industry commentary rather than a single settled provision, so this engine surfaces
its reasoning explicitly rather than presenting a bare "blocked"/"not blocked" answer.

Uses app.core.geo (already-fixed region-matching logic) for the data-localization
exposure check — it does not reimplement region comparison.
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.geo import location_in_countries
from app.models.data_asset import DataAsset

RETENTION_FLOORS: dict[str, dict[str, object]] = {
    "kyc_identity_documents": {
        "floor_years": 5,
        "authority": "RBI Master Direction - Know Your Customer (KYC) Direction, 2016 (as amended)",
        "citation": "Records of identification of customers are to be retained for five years "
        "after the business relationship ends.",
    },
    "transaction_records": {
        "floor_years": 5,
        "authority": "Prevention of Money Laundering Act, 2002 read with PML (Maintenance of "
        "Records) Rules, 2005",
        "citation": "Transaction records are to be maintained for five years from the date of "
        "the transaction / end of the business relationship, whichever is later.",
    },
}

DPDP_RETENTION_FLOOR_BASIS = (
    "DPDP Act 2023 Section 8(5)/Section 12 permits retention beyond the purpose-limitation "
    "default where another law in force requires it; the RBI/PMLA retention floor therefore "
    "governs until it lapses, and DPDP erasure only becomes available once that floor has passed."
)

INDIA_PAYMENT_LOCALIZATION_AUTHORITY = (
    "RBI circular DPSS.CO.OD No.2785/06.08.005/2017-2018 (06-Apr-2018), 'Storage of Payment "
    "System Data' — complete end-to-end payment system data must be stored only in India; "
    "processing abroad is permitted but data must not be retained outside India."
)


class RBIDPDPReconciliationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def explain(
        self,
        org_id: uuid.UUID,
        data_category: str,
        relationship_end_date: dt.date | None = None,
        today: dt.date | None = None,
    ) -> dict:
        _ = org_id  # reserved for org-specific retention policy overrides in a future pass
        today = today or dt.date.today()
        floor = RETENTION_FLOORS.get(data_category)

        if floor is None:
            return {
                "data_category": data_category,
                "blocked": False,
                "reason": "No RBI/PMLA retention floor is mapped for this data category; "
                "DPDP purpose-limitation/erasure governs directly.",
                "retention_until": None,
                "erasure_available_from": None,
                "citations": [],
            }

        if relationship_end_date is None:
            return {
                "data_category": data_category,
                "blocked": True,
                "reason": (
                    f"{floor['authority']} requires retention for {floor['floor_years']} years "
                    "from the end of the customer relationship, but no relationship/account-"
                    "closure end date is on file for this request — the exact retention-floor "
                    "expiry cannot be confirmed. Flagged for manual legal/compliance review "
                    "rather than assumed erasable."
                ),
                "retention_until": None,
                "erasure_available_from": None,
                "citations": [floor["citation"], DPDP_RETENTION_FLOOR_BASIS],
            }

        retention_until = relationship_end_date.replace(year=relationship_end_date.year + int(floor["floor_years"]))
        blocked = today < retention_until
        return {
            "data_category": data_category,
            "blocked": blocked,
            "reason": (
                f"Blocked because {floor['authority']} requires retention until {retention_until.isoformat()}; "
                f"DPDP erasure becomes available on {retention_until.isoformat()}."
                if blocked
                else f"{floor['authority']}'s {floor['floor_years']}-year retention floor lapsed on "
                f"{retention_until.isoformat()}; DPDP erasure may now proceed."
            ),
            "retention_until": retention_until.isoformat(),
            "erasure_available_from": retention_until.isoformat(),
            "citations": [floor["citation"], DPDP_RETENTION_FLOOR_BASIS],
        }

    def check_payment_data_localization_exposure(self, org_id: uuid.UUID) -> list[dict]:
        """Flag financial_data assets whose geographic_locations are not fully confined to
        India, per the stricter RBI payment-data-localization standard (DPDP itself is more
        permissive by default)."""
        assets = self.db.execute(
            select(DataAsset).where(
                DataAsset.organization_id == org_id,
                DataAsset.classification_type == "financial_data",
            )
        ).scalars().all()

        exposures = []
        for asset in assets:
            locations = asset.geographic_locations or []
            if not locations or not all(location_in_countries(loc, {"IN"}) for loc in locations):
                exposures.append(
                    {
                        "data_asset_id": asset.id,
                        "asset_name": asset.name,
                        "geographic_locations": locations,
                        "authority": INDIA_PAYMENT_LOCALIZATION_AUTHORITY,
                        "reason": "Financial data asset is not confined to India-only locations; "
                        "RBI's payment-data-localization circular is stricter than DPDP's default "
                        "cross-border permissiveness.",
                    }
                )
        return exposures
