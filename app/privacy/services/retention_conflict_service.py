"""Pluggable hook for legal-retention conflict checks on DSAR erasure requests.

This module is the seam between app.privacy.services.dsar_service (which calls
check_retention_conflict() before letting an 'erasure' request transition to
'fulfilled') and the RBI-DPDP reconciliation engine
(app.privacy.services.rbi_dpdp_reconciliation_service.RBIDPDPReconciliationService),
which supplies the real KYC/PMLA retention-floor logic.
"""

import datetime as dt
import uuid

from sqlalchemy.orm import Session


def check_retention_conflict(
    db: Session,
    org_id: uuid.UUID,
    data_categories: list[str],
    relationship_end_date: dt.date | None = None,
) -> dict | None:
    """Return a conflict dict with a 'conflicts' list (one explainable entry per blocked
    data category, per RBIDPDPReconciliationService.explain) if any of the given
    data_categories has an unexpired or unconfirmed legal-retention requirement, or None
    if there is no conflict for any category."""
    from app.privacy.services.rbi_dpdp_reconciliation_service import RBIDPDPReconciliationService

    if not data_categories:
        return None

    service = RBIDPDPReconciliationService(db)
    conflicts = [
        result
        for category in data_categories
        if (result := service.explain(org_id, category, relationship_end_date=relationship_end_date))["blocked"]
    ]
    if not conflicts:
        return None
    return {"conflicts": conflicts}
