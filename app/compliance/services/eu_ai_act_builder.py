import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.regulatory_report_registry import REGULATORY_REPORT_REGISTRY
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState


RISK_TIERS = {
    "prohibited": "Prohibited AI Practices (Art. 5)",
    "high_risk": "High-Risk AI Systems (Art. 6-51)",
    "limited_risk": "Limited Risk (Art. 52)",
    "minimal_risk": "Minimal Risk (Art. 53)",
}


class EUAIActConformityBuilder:
    report_type = "eu_ai_act_conformity"

    @staticmethod
    def _find_framework(org_id: uuid.UUID, db: Session) -> Framework | None:
        return db.execute(
            select(Framework)
            .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
            .where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.status == "active",
                (Framework.name.ilike("%eu%ai%act%") | Framework.name.ilike("%ai act%") | Framework.code.ilike("%ai%act%")),
            )
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _extract_article(reference_code: str | None) -> int | None:
        if not reference_code:
            return None
        m = re.search(r"(?:Art\.?\s*)(\d+)", reference_code, re.IGNORECASE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except ValueError:
            return None

    @staticmethod
    def _tier_for_article(article: int | None) -> str | None:
        if article is None:
            return None
        if article == 5:
            return "prohibited"
        if 6 <= article <= 51:
            return "high_risk"
        if article == 52:
            return "limited_risk"
        if article == 53:
            return "minimal_risk"
        return None

    @staticmethod
    def build(org_id: uuid.UUID, db: Session) -> dict:
        framework = EUAIActConformityBuilder._find_framework(org_id, db)
        if framework is None:
            return {
                "report_type": "eu_ai_act_conformity",
                "status": "not_applicable",
                "message": "EU AI Act framework not configured.",
            }

        obligations = db.execute(
            select(Obligation)
            .where(
                Obligation.framework_id == framework.id,
                Obligation.status == "active",
            )
            .order_by(Obligation.reference_code.asc())
        ).scalars().all()
        states = {
            row.obligation_id: row
            for row in db.execute(
                select(OrganizationObligationState).where(OrganizationObligationState.organization_id == org_id)
            ).scalars().all()
        }

        buckets = {key: [] for key in RISK_TIERS}
        for ob in obligations:
            tier = EUAIActConformityBuilder._tier_for_article(EUAIActConformityBuilder._extract_article(ob.reference_code))
            if tier:
                buckets[tier].append(ob)

        tier_rows: list[dict] = []
        total = covered_total = 0
        for tier, label in RISK_TIERS.items():
            items = buckets[tier]
            covered = 0
            for ob in items:
                st = states.get(ob.id)
                if st and (st.implementation_status or "").lower() in {"met", "implemented"}:
                    covered += 1
            total_tier = len(items)
            coverage = round((covered / total_tier) * 100.0, 2) if total_tier else 0.0
            total += total_tier
            covered_total += covered
            tier_rows.append(
                {
                    "tier": tier,
                    "label": label,
                    "total_requirements": total_tier,
                    "covered": covered,
                    "coverage_pct": coverage,
                }
            )

        overall = round((covered_total / total) * 100.0, 2) if total else 0.0
        return {
            "report_type": "eu_ai_act_conformity",
            "framework": framework.name,
            "risk_tiers": tier_rows,
            "overall_conformity_pct": overall,
            "note": (
                "EU AI Act conformity depends on your AI system classifications. "
                "Ensure AI vendor assessments are complete."
            ),
        }


REGULATORY_REPORT_REGISTRY[EUAIActConformityBuilder.report_type] = EUAIActConformityBuilder
