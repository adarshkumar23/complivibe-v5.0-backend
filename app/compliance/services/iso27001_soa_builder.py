import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.regulatory_report_registry import REGULATORY_REPORT_REGISTRY
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState


ANNEX_A_DOMAINS = {
    "A.5": "Information Security Policies",
    "A.6": "Organization of Information Security",
    "A.7": "Human Resource Security",
    "A.8": "Asset Management",
    "A.9": "Access Control",
    "A.10": "Cryptography",
    "A.11": "Physical and Environmental Security",
    "A.12": "Operations Security",
    "A.13": "Communications Security",
    "A.14": "System Acquisition, Development & Maintenance",
    "A.15": "Supplier Relationships",
    "A.16": "Information Security Incident Management",
    "A.17": "Business Continuity Management",
    "A.18": "Compliance",
}


class ISO27001SOABuilder:
    report_type = "iso27001_soa"

    @staticmethod
    def _find_framework(org_id: uuid.UUID, db: Session) -> Framework | None:
        return db.execute(
            select(Framework)
            .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
            .where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.status == "active",
                Framework.name.ilike("%iso%27001%"),
            )
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _impl_status(value: str | None) -> str:
        normalized = (value or "").lower().strip()
        if normalized in {"implemented", "met"}:
            return "implemented"
        if normalized in {"in_progress", "partial", "partially_implemented", "partially_met"}:
            return "partial"
        return "not_implemented"

    @staticmethod
    def build(org_id: uuid.UUID, db: Session) -> dict:
        framework = ISO27001SOABuilder._find_framework(org_id, db)
        if framework is None:
            return {
                "report_type": "iso27001_soa",
                "status": "not_applicable",
                "message": "ISO 27001 framework not configured.",
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

        domains: list[dict] = []
        implemented = partial = not_implemented = total = 0

        for code, name in ANNEX_A_DOMAINS.items():
            domain_obs = [ob for ob in obligations if (ob.reference_code or "").upper().startswith(code.upper())]
            if not domain_obs:
                continue

            controls: list[dict] = []
            for ob in domain_obs:
                state = states.get(ob.id)
                impl = ISO27001SOABuilder._impl_status(state.implementation_status if state else None)
                if impl == "implemented":
                    implemented += 1
                elif impl == "partial":
                    partial += 1
                else:
                    not_implemented += 1
                total += 1

                justification = (ob.description or "")[:200]
                controls.append(
                    {
                        "ref": ob.reference_code,
                        "title": ob.title,
                        "applicability": "applicable",
                        "implementation_status": impl,
                        "justification": justification,
                    }
                )

            domains.append({"code": code, "name": name, "controls": controls})

        pct = round((implemented / total) * 100.0, 2) if total else 0.0
        return {
            "report_type": "iso27001_soa",
            "framework": framework.name,
            "domains": domains,
            "summary": {
                "total": total,
                "implemented": implemented,
                "partial": partial,
                "not_implemented": not_implemented,
                "implementation_pct": pct,
            },
        }


REGULATORY_REPORT_REGISTRY[ISO27001SOABuilder.report_type] = ISO27001SOABuilder
