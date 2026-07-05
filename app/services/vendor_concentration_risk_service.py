from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.risk import Risk
from app.models.vendor import Vendor
from app.models.vendor_concentration_risk import VendorConcentrationRiskDetection
from app.models.vendor_supply_chain import VendorSupplyChainLink
from app.services.risk_service import RiskService


HHI_HIGHLY_CONCENTRATED_THRESHOLD = 1800
CONCENTRATION_SOURCE_TITLE = "U.S. DOJ and FTC 2023 Merger Guidelines, Guideline 1"
CONCENTRATION_SOURCE_URL = "https://www.justice.gov/atr/merger-guidelines/applying-merger-guidelines/guideline-1"
CRITICALITY_SOURCE_TITLE = "Interagency Guidance on Third-Party Relationships: Risk Management"
CRITICALITY_SOURCE_URL = "https://www.federalregister.gov/documents/2023/06/09/2023-12340/interagency-guidance-on-third-party-relationships-risk-management"
CRITICAL_RISK_TIERS = {"critical", "high"}


class VendorConcentrationRiskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def current(self, organization_id: uuid.UUID) -> VendorConcentrationRiskDetection | None:
        return self.db.execute(
            select(VendorConcentrationRiskDetection).where(
                VendorConcentrationRiskDetection.organization_id == organization_id
            )
        ).scalar_one_or_none()

    def recompute(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        threshold_hhi_score: int = HHI_HIGHLY_CONCENTRATED_THRESHOLD,
    ) -> tuple[VendorConcentrationRiskDetection, bool, bool]:
        result = self._calculate(organization_id=organization_id, threshold_hhi_score=threshold_hhi_score)
        existing = self.current(organization_id)
        before = self._state_fingerprint(existing) if existing is not None else None
        risk_created = False

        if existing is None:
            existing = VendorConcentrationRiskDetection(organization_id=organization_id)
            self.db.add(existing)

        existing.status = result["status"]
        existing.hhi_score = result["hhi_score"]
        existing.threshold_hhi_score = threshold_hhi_score
        existing.top_vendor_id = result["top_vendor_id"]
        existing.top_vendor_name = result["top_vendor_name"]
        existing.top_vendor_share_basis_points = result["top_vendor_share_basis_points"]
        existing.exposure_count = result["exposure_count"]
        existing.critical_vendor_count = result["critical_vendor_count"]
        existing.dependency_count = result["dependency_count"]
        existing.convention_source_title = CONCENTRATION_SOURCE_TITLE
        existing.convention_source_url = CONCENTRATION_SOURCE_URL
        existing.criticality_source_title = CRITICALITY_SOURCE_TITLE
        existing.criticality_source_url = CRITICALITY_SOURCE_URL
        existing.evidence_json = result["evidence_json"]
        existing.recomputed_by_user_id = actor_user_id
        existing.recomputed_at = datetime.now(UTC)
        self.db.flush()

        if existing.status == "breach" and existing.risk_id is None:
            risk = self._create_register_risk(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                detection=existing,
            )
            existing.risk_id = risk.id
            risk_created = True
            self.db.flush()

        after = self._state_fingerprint(existing)
        return existing, risk_created, before != after

    def _calculate(self, *, organization_id: uuid.UUID, threshold_hhi_score: int) -> dict[str, Any]:
        vendors = self.db.execute(
            select(Vendor).where(
                Vendor.organization_id == organization_id,
                Vendor.status != "archived",
                Vendor.archived_at.is_(None),
            )
        ).scalars().all()
        vendors_by_id = {vendor.id: vendor for vendor in vendors}
        critical_vendor_ids = {
            vendor.id
            for vendor in vendors
            if (vendor.risk_tier or "").strip().lower() in CRITICAL_RISK_TIERS and vendor.status == "active"
        }

        exposures: list[uuid.UUID] = list(critical_vendor_ids)
        links = self.db.execute(
            select(VendorSupplyChainLink).where(
                VendorSupplyChainLink.organization_id == organization_id,
                VendorSupplyChainLink.is_active.is_(True),
            )
        ).scalars().all()
        dependency_count = 0
        for link in links:
            parent = vendors_by_id.get(link.parent_vendor_id)
            sub_vendor = vendors_by_id.get(link.sub_vendor_id)
            if parent is None or sub_vendor is None:
                continue
            if parent.id not in critical_vendor_ids:
                continue
            if sub_vendor.status != "active":
                continue
            exposures.append(sub_vendor.id)
            dependency_count += 1

        exposure_count = len(exposures)
        counts = Counter(exposures)
        shares = []
        hhi_score = 0
        for vendor_id, count in counts.items():
            share_basis_points = round((count / exposure_count) * 10000) if exposure_count else 0
            share_percent = share_basis_points / 100
            hhi_score += round(share_percent * share_percent)
            vendor = vendors_by_id.get(vendor_id)
            shares.append(
                {
                    "vendor_id": str(vendor_id),
                    "vendor_name": vendor.name if vendor is not None else "Unknown vendor",
                    "exposure_count": count,
                    "share_basis_points": share_basis_points,
                }
            )
        shares.sort(key=lambda row: (-row["exposure_count"], row["vendor_name"]))
        top = shares[0] if shares else None

        return {
            "status": "breach" if hhi_score >= threshold_hhi_score and exposure_count > 0 else "below_threshold",
            "hhi_score": hhi_score,
            "top_vendor_id": uuid.UUID(top["vendor_id"]) if top else None,
            "top_vendor_name": top["vendor_name"] if top else None,
            "top_vendor_share_basis_points": top["share_basis_points"] if top else 0,
            "exposure_count": exposure_count,
            "critical_vendor_count": len(critical_vendor_ids),
            "dependency_count": dependency_count,
            "evidence_json": {
                "metric": "herfindahl_hirschman_index",
                "vendor_shares": shares,
                "critical_vendor_risk_tiers": sorted(CRITICAL_RISK_TIERS),
            },
        }

    def _create_register_risk(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        detection: VendorConcentrationRiskDetection,
    ) -> Risk:
        top_vendor = detection.top_vendor_name or "unknown vendor"
        description = (
            f"Vendor concentration detection found an HHI score of {detection.hhi_score} "
            f"against the {detection.threshold_hhi_score} highly concentrated threshold. "
            f"{top_vendor} represents {detection.top_vendor_share_basis_points / 100:.2f}% "
            "of critical vendor and dependency exposure."
        )
        metadata = {
            "source": "vendor_concentration_risk",
            "detection_id": str(detection.id),
            "hhi_score": detection.hhi_score,
            "threshold_hhi_score": detection.threshold_hhi_score,
            "top_vendor_id": str(detection.top_vendor_id) if detection.top_vendor_id else None,
            "convention_source_url": detection.convention_source_url,
            "criticality_source_url": detection.criticality_source_url,
        }
        return RiskService(self.db).create_risk_from_service(
            organization_id=organization_id,
            title=f"Vendor concentration risk: {top_vendor}",
            description=description,
            category="vendor",
            likelihood=4,
            impact=4 if detection.hhi_score < 2500 else 5,
            treatment_strategy="mitigate",
            risk_context_external=(
                "Concentration score uses the Herfindahl-Hirschman Index convention from "
                f"{CONCENTRATION_SOURCE_TITLE}. Critical vendor/dependency scoping follows "
                f"{CRITICALITY_SOURCE_TITLE}."
            ),
            metadata_json=metadata,
            created_by_user_id=actor_user_id,
            audit_source="vendor_concentration_risk",
        )

    @staticmethod
    def _state_fingerprint(detection: VendorConcentrationRiskDetection | None) -> dict | None:
        if detection is None:
            return None
        return {
            "status": detection.status,
            "hhi_score": detection.hhi_score,
            "threshold_hhi_score": detection.threshold_hhi_score,
            "top_vendor_id": str(detection.top_vendor_id) if detection.top_vendor_id else None,
            "top_vendor_share_basis_points": detection.top_vendor_share_basis_points,
            "exposure_count": detection.exposure_count,
            "critical_vendor_count": detection.critical_vendor_count,
            "dependency_count": detection.dependency_count,
            "risk_id": str(detection.risk_id) if detection.risk_id else None,
        }
