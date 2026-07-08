import uuid
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vendor import Vendor
from app.models.vendor_criticality import VendorCriticalityProfile, VendorCriticalitySetting
from app.schemas.vendor_criticality import VendorCriticalityProfileUpdate, VendorCriticalitySettingUpdate
from app.services.audit_service import AuditService

# A business-criticality profile is a point-in-time judgment call (revenue share, data
# volume, operational importance, substitutability). Unlike security-rating or threat-
# intelligence signals it is never auto-recomputed, so it can silently go stale for far
# longer - a vendor can go from a pilot to a core revenue dependency over a year without
# anyone revisiting this profile. Mirrors the is_stale/age_days pattern used across the
# other TPRM intelligence signals (sanctions, KYB, threat intel) so staleness reads the
# same way everywhere in this API.
CRITICALITY_STALE_AFTER_DAYS = 180

DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "revenue_dependency_weight": Decimal("0.2500"),
    "data_volume_weight": Decimal("0.2500"),
    "operational_criticality_weight": Decimal("0.2500"),
    "substitutability_weight": Decimal("0.2500"),
}

DATA_VOLUME_VALUES: dict[str, Decimal] = {
    "none": Decimal("0"),
    "low": Decimal("1"),
    "medium": Decimal("3"),
    "high": Decimal("4"),
    "very_high": Decimal("5"),
}

OPERATIONAL_VALUES: dict[str, Decimal] = {
    "low": Decimal("1"),
    "medium": Decimal("3"),
    "high": Decimal("4"),
    "critical": Decimal("5"),
}


class VendorCriticalityService:
    """Business-criticality weighted vendor scoring.

    Formula notes for reviewers:
    - NIST CSF 2.0 GV.SC-04: suppliers should be known and prioritized by criticality.
      https://www.nist.gov/cyberframework
    - NIST SP 800-161 Rev. 1 recommends contextualizing supply-chain risk exposure
      against critical operations and enterprise risk categories such as financial and
      strategic risk. https://csrc.nist.gov/pubs/sp/800/161/r1/upd1/final
    - FFIEC Outsourcing Technology Services guidance frames outsourcing risk
      assessment around the service/provider risk profile and critical business
      impact. https://ithandbook.ffiec.gov/it-booklets/outsourcing-technology-services

    The score intentionally separates business criticality from likelihood x impact
    risk history: profile drivers are normalized to 0-5, configurable org weights
    are applied, and the weighted result is projected to 0-100.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def require_vendor_in_org(self, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> Vendor:
        row = self.db.execute(
            select(Vendor).where(
                Vendor.id == vendor_id,
                Vendor.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")
        return row

    def get_settings(self, organization_id: uuid.UUID) -> VendorCriticalitySetting | None:
        return self.db.execute(
            select(VendorCriticalitySetting).where(VendorCriticalitySetting.organization_id == organization_id)
        ).scalar_one_or_none()

    def get_profile(self, organization_id: uuid.UUID, vendor_id: uuid.UUID) -> VendorCriticalityProfile | None:
        return self.db.execute(
            select(VendorCriticalityProfile).where(
                VendorCriticalityProfile.organization_id == organization_id,
                VendorCriticalityProfile.vendor_id == vendor_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def settings_weights(settings: VendorCriticalitySetting | None) -> dict[str, Decimal]:
        if settings is None:
            return DEFAULT_WEIGHTS.copy()
        return {
            "revenue_dependency_weight": Decimal(settings.revenue_dependency_weight),
            "data_volume_weight": Decimal(settings.data_volume_weight),
            "operational_criticality_weight": Decimal(settings.operational_criticality_weight),
            "substitutability_weight": Decimal(settings.substitutability_weight),
        }

    @staticmethod
    def criticality_tier_from_score(score: int) -> str:
        if score <= 25:
            return "low"
        if score <= 50:
            return "medium"
        if score <= 75:
            return "high"
        return "critical"

    @classmethod
    def compute_score_payload(
        cls,
        *,
        revenue_dependency_pct: Decimal,
        data_volume_tier: str,
        operational_criticality: str,
        substitutability_score: int,
        weights: dict[str, Decimal],
    ) -> tuple[int, str, dict[str, Any]]:
        revenue_value = min(Decimal("5"), max(Decimal("0"), Decimal(revenue_dependency_pct) / Decimal("20")))
        data_volume_value = DATA_VOLUME_VALUES[data_volume_tier]
        operational_value = OPERATIONAL_VALUES[operational_criticality]
        substitutability_value = Decimal(substitutability_score)

        total_weight = sum(weights.values(), Decimal("0"))
        if total_weight <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one criticality weight must be greater than zero")

        weighted_0_to_5 = (
            revenue_value * weights["revenue_dependency_weight"]
            + data_volume_value * weights["data_volume_weight"]
            + operational_value * weights["operational_criticality_weight"]
            + substitutability_value * weights["substitutability_weight"]
        ) / total_weight
        score = int(((weighted_0_to_5 / Decimal("5")) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        tier = cls.criticality_tier_from_score(score)
        explanation = {
            "inputs": {
                "revenue_dependency_pct": str(revenue_dependency_pct),
                "data_volume_tier": data_volume_tier,
                "operational_criticality": operational_criticality,
                "substitutability_score": substitutability_score,
            },
            "normalized_values_0_to_5": {
                "revenue_dependency": str(revenue_value.quantize(Decimal("0.01"))),
                "data_volume": str(data_volume_value),
                "operational_criticality": str(operational_value),
                "substitutability": str(substitutability_value),
            },
            "weights": {key: str(value) for key, value in weights.items()},
            "formula": "round_0_100(sum(normalized_0_to_5 * weight) / sum(weights) / 5 * 100)",
            "thresholds": {
                "low": [0, 25],
                "medium": [26, 50],
                "high": [51, 75],
                "critical": [76, 100],
            },
            "sources": [
                "NIST CSF 2.0 GV.SC-04 supplier criticality prioritization",
                "NIST SP 800-161 Rev. 1 supply-chain risk context for critical operations",
                "FFIEC Outsourcing Technology Services risk assessment guidance",
            ],
            "provenance": "vendor_business_criticality_weighted_v1",
        }
        return score, tier, explanation

    @staticmethod
    def build_priority_context(vendor: Vendor, criticality_tier: str) -> dict[str, Any]:
        """Cross-reference business criticality against the vendor's independently
        assessed risk state, without overwriting either signal.

        ``Vendor.risk_tier`` is owned by ``VendorRiskService`` (manual likelihood x
        impact scoring) and questionnaire answer-rule scoring - it reflects assessed
        risk, not business importance. Criticality must never overwrite it (doing so
        previously let a routine business-criticality update silently erase a
        vendor's real "critical" risk assessment down to "low"). Instead we surface
        an explicit recommendation when the two signals are misaligned or when other
        platform state (nth-party risk flags) hasn't been reconciled with criticality.
        Computed fresh on every read so it reflects the vendor's CURRENT state
        (e.g. a sanctions hit or a T1-3 nth-party flag raised after this profile
        was last saved).
        """
        risk_tier = (vendor.risk_tier or "not_assessed").lower()
        elevated_criticality = criticality_tier in ("high", "critical")
        elevated_risk = risk_tier in ("high", "critical")

        if elevated_criticality and risk_tier == "not_assessed":
            recommendation = (
                "Business-critical vendor has no risk assessment on file - prioritize a "
                "likelihood x impact review."
            )
        elif elevated_criticality and vendor.nth_party_risk_flag:
            recommendation = (
                "Business-critical vendor has an active nth-party risk flag "
                f"({vendor.nth_party_risk_severity or 'unspecified'} severity) - escalate for review."
            )
        elif elevated_criticality and not elevated_risk:
            recommendation = (
                f"Business-critical vendor's assessed risk tier is only '{risk_tier}' - verify the "
                "risk assessment is current."
            )
        elif not elevated_criticality and elevated_risk:
            recommendation = (
                f"Vendor's assessed risk tier ('{risk_tier}') exceeds its business criticality tier "
                f"('{criticality_tier}') - risk drivers other than business importance are dominating; no "
                "criticality action needed."
            )
        else:
            recommendation = "Business criticality and assessed risk tier are aligned; no escalation signal."

        return {
            "current_risk_tier": vendor.risk_tier,
            "nth_party_risk_flag": vendor.nth_party_risk_flag,
            "nth_party_risk_severity": vendor.nth_party_risk_severity,
            "recommendation": recommendation,
        }

    def default_profile_payload(self, organization_id: uuid.UUID, vendor: Vendor) -> dict[str, Any]:
        score, tier, explanation = self.compute_score_payload(
            revenue_dependency_pct=Decimal("0.00"),
            data_volume_tier="none",
            operational_criticality="low",
            substitutability_score=1,
            weights=self.settings_weights(self.get_settings(organization_id)),
        )
        now = datetime.now(UTC)
        return {
            "id": None,
            "organization_id": organization_id,
            "vendor_id": vendor.id,
            "revenue_dependency_pct": Decimal("0.00"),
            "data_volume_tier": "none",
            "operational_criticality": "low",
            "substitutability_score": 1,
            "criticality_score": score,
            "criticality_tier": tier,
            "score_explanation_json": explanation,
            "priority_context": self.build_priority_context(vendor, tier),
            "notes": None,
            "updated_by_user_id": None,
            "created_at": None,
            "updated_at": now,
            "is_default": True,
            "profile_age_days": None,
            "is_stale": True,
            "stale_after_days": CRITICALITY_STALE_AFTER_DAYS,
            "context_flags": ["no_profile_configured"],
        }

    @staticmethod
    def staleness_context(updated_at: datetime | None) -> dict[str, Any]:
        if updated_at is None:
            return {"profile_age_days": None, "is_stale": True, "stale_after_days": CRITICALITY_STALE_AFTER_DAYS}
        aware_updated_at = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
        age_days = round((datetime.now(UTC) - aware_updated_at).total_seconds() / 86400.0, 2)
        return {
            "profile_age_days": age_days,
            "is_stale": age_days > CRITICALITY_STALE_AFTER_DAYS,
            "stale_after_days": CRITICALITY_STALE_AFTER_DAYS,
        }

    @staticmethod
    def settings_before_after(row: VendorCriticalitySetting | None) -> dict[str, str] | None:
        if row is None:
            return None
        return {
            "revenue_dependency_weight": str(row.revenue_dependency_weight),
            "data_volume_weight": str(row.data_volume_weight),
            "operational_criticality_weight": str(row.operational_criticality_weight),
            "substitutability_weight": str(row.substitutability_weight),
        }

    def upsert_settings(
        self,
        *,
        organization_id: uuid.UUID,
        payload: VendorCriticalitySettingUpdate,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VendorCriticalitySetting:
        row = self.get_settings(organization_id)
        before = self.settings_before_after(row)
        if row is None:
            row = VendorCriticalitySetting(organization_id=organization_id)
            self.db.add(row)

        row.revenue_dependency_weight = payload.revenue_dependency_weight
        row.data_volume_weight = payload.data_volume_weight
        row.operational_criticality_weight = payload.operational_criticality_weight
        row.substitutability_weight = payload.substitutability_weight
        row.updated_by_user_id = actor_user_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_criticality_settings.updated",
            entity_type="vendor_criticality_settings",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self.settings_before_after(row),
            metadata_json={"source": "api"},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return row

    def upsert_profile(
        self,
        *,
        organization_id: uuid.UUID,
        vendor_id: uuid.UUID,
        payload: VendorCriticalityProfileUpdate,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> VendorCriticalityProfile:
        vendor = self.require_vendor_in_org(organization_id, vendor_id)
        # Consistent with every other TPRM intelligence signal in this API (sanctions
        # screening, KYB/AML checks, security rating, threat intelligence, and now
        # supply-chain linking all reject archived vendors): an offboarded vendor
        # shouldn't gain a fresh business-criticality judgment call.
        if vendor.status == "archived":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Archived vendors cannot have their criticality profile updated")
        row = self.get_profile(organization_id, vendor_id)
        before = self.profile_audit_payload(row)
        if row is None:
            row = VendorCriticalityProfile(organization_id=organization_id, vendor_id=vendor_id, updated_by_user_id=actor_user_id)
            self.db.add(row)

        score, tier, explanation = self.compute_score_payload(
            revenue_dependency_pct=payload.revenue_dependency_pct,
            data_volume_tier=payload.data_volume_tier,
            operational_criticality=payload.operational_criticality,
            substitutability_score=payload.substitutability_score,
            weights=self.settings_weights(self.get_settings(organization_id)),
        )

        row.revenue_dependency_pct = payload.revenue_dependency_pct
        row.data_volume_tier = payload.data_volume_tier
        row.operational_criticality = payload.operational_criticality
        row.substitutability_score = payload.substitutability_score
        row.criticality_score = score
        row.criticality_tier = tier
        row.score_explanation_json = explanation
        row.notes = payload.notes
        row.updated_by_user_id = actor_user_id
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="vendor_criticality_profile.updated",
            entity_type="vendor_criticality_profile",
            entity_id=row.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self.profile_audit_payload(row),
            metadata_json={"source": "api", "vendor_id": str(vendor_id)},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        # NOTE: business criticality intentionally never writes to Vendor.risk_tier
        # (see build_priority_context docstring for why). Previously this method
        # overwrote vendor.risk_tier with the criticality tier here, which meant a
        # routine business-criticality update could silently erase a vendor's real
        # "critical" risk assessment down to "low". That has been removed; the two
        # signals are cross-referenced instead of clobbered.
        return row

    @staticmethod
    def profile_audit_payload(row: VendorCriticalityProfile | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "vendor_id": str(row.vendor_id),
            "revenue_dependency_pct": str(row.revenue_dependency_pct),
            "data_volume_tier": row.data_volume_tier,
            "operational_criticality": row.operational_criticality,
            "substitutability_score": row.substitutability_score,
            "criticality_score": row.criticality_score,
            "criticality_tier": row.criticality_tier,
        }
