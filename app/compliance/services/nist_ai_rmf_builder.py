import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.regulatory_report_registry import REGULATORY_REPORT_REGISTRY
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState


FUNCTIONS = ["GOVERN", "MAP", "MEASURE", "MANAGE"]


class NISTAIRMFSummaryBuilder:
    report_type = "nist_ai_rmf_summary"

    @staticmethod
    def _find_framework(org_id: uuid.UUID, db: Session) -> Framework | None:
        return db.execute(
            select(Framework)
            .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
            .where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.status == "active",
                (Framework.name.ilike("%nist%ai%") | Framework.name.ilike("%ai rmf%") | Framework.code.ilike("%ai%rmf%")),
            )
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def build(org_id: uuid.UUID, db: Session) -> dict:
        framework = NISTAIRMFSummaryBuilder._find_framework(org_id, db)
        if framework is None:
            return {
                "report_type": "nist_ai_rmf_summary",
                "status": "not_applicable",
                "message": "NIST AI RMF framework not configured.",
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

        function_rows: list[dict] = []
        total = covered_total = 0
        for fn in FUNCTIONS:
            fn_obs = [ob for ob in obligations if (ob.reference_code or "").upper().startswith(fn)]
            total_fn = len(fn_obs)
            covered = 0
            gaps: list[str] = []
            for ob in fn_obs:
                state = states.get(ob.id)
                if state and (state.implementation_status or "").lower() in {"met", "implemented"}:
                    covered += 1
                else:
                    gaps.append(ob.title)

            total += total_fn
            covered_total += covered
            coverage = round((covered / total_fn) * 100.0, 2) if total_fn else 0.0
            function_rows.append(
                {
                    "name": fn,
                    "total_subcategories": total_fn,
                    "covered": covered,
                    "coverage_pct": coverage,
                    "key_gaps": gaps[:3],
                }
            )

        overall = round((covered_total / total) * 100.0, 2) if total else 0.0
        return {
            "report_type": "nist_ai_rmf_summary",
            "framework": framework.name,
            "functions": function_rows,
            "overall_coverage_pct": overall,
        }


REGULATORY_REPORT_REGISTRY[NISTAIRMFSummaryBuilder.report_type] = NISTAIRMFSummaryBuilder
