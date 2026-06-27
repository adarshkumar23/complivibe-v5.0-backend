import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.regulatory_report_registry import REGULATORY_REPORT_REGISTRY
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.framework import Framework
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState


TSC_CATEGORIES = {
    "CC1": "Control Environment",
    "CC2": "Communication and Information",
    "CC3": "Risk Assessment",
    "CC4": "Monitoring Activities",
    "CC5": "Control Activities",
    "CC6": "Logical and Physical Access",
    "CC7": "System Operations",
    "CC8": "Change Management",
    "CC9": "Risk Mitigation",
    "A1": "Availability",
    "C1": "Confidentiality",
    "PI1": "Processing Integrity",
    "P1": "Privacy",
}


class SOC2ReadinessReportBuilder:
    report_type = "soc2_readiness"

    @staticmethod
    def _find_framework(org_id: uuid.UUID, db: Session) -> Framework | None:
        return db.execute(
            select(Framework)
            .join(OrganizationFramework, OrganizationFramework.framework_id == Framework.id)
            .where(
                OrganizationFramework.organization_id == org_id,
                OrganizationFramework.status == "active",
                (Framework.name.ilike("%soc 2%") | Framework.name.ilike("%soc2%") | Framework.code.ilike("%soc2%")),
            )
            .order_by(Framework.name.asc())
            .limit(1)
        ).scalar_one_or_none()

    @staticmethod
    def _state_to_readiness(implementation_status: str | None, controls_linked: int) -> str:
        normalized = (implementation_status or "").lower().strip()
        if normalized in {"met", "implemented"}:
            return "ready"
        if controls_linked > 0:
            return "partial"
        return "not_ready"

    @staticmethod
    def _normalize_uuid_list(values: list) -> list[uuid.UUID]:
        normalized: list[uuid.UUID] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, uuid.UUID):
                normalized.append(value)
            else:
                normalized.append(uuid.UUID(str(value)))
        return normalized

    @staticmethod
    def build(org_id: uuid.UUID, db: Session) -> dict:
        now = datetime.now(UTC)
        framework = SOC2ReadinessReportBuilder._find_framework(org_id, db)
        if framework is None:
            return {
                "report_type": "soc2_readiness",
                "status": "not_applicable",
                "message": "SOC 2 framework not configured.",
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

        summary_total = 0
        summary_ready = 0
        summary_partial = 0
        summary_not_ready = 0
        categories: list[dict] = []

        for code, name in TSC_CATEGORIES.items():
            matching = [ob for ob in obligations if (ob.reference_code or "").upper().startswith(code.upper())]
            criteria: list[dict] = []
            ready = partial = not_ready = 0

            for obligation in matching:
                controls_linked = int(
                    db.execute(
                        select(func.count(func.distinct(ControlObligationMapping.control_id))).where(
                            ControlObligationMapping.organization_id == org_id,
                            ControlObligationMapping.obligation_id == obligation.id,
                            ControlObligationMapping.status == "active",
                        )
                    ).scalar_one()
                )

                control_ids = db.execute(
                    select(func.distinct(ControlObligationMapping.control_id))
                    .join(Control, Control.id == ControlObligationMapping.control_id)
                    .where(
                        ControlObligationMapping.organization_id == org_id,
                        ControlObligationMapping.obligation_id == obligation.id,
                        ControlObligationMapping.status == "active",
                        Control.organization_id == org_id,
                        Control.status != "archived",
                    )
                ).scalars().all()
                control_ids = SOC2ReadinessReportBuilder._normalize_uuid_list(control_ids)

                evidence_count = 0
                if control_ids:
                    evidence_count = int(
                        db.execute(
                            select(func.count(func.distinct(EvidenceItem.id)))
                            .join(EvidenceControlLink, EvidenceControlLink.evidence_item_id == EvidenceItem.id)
                            .where(
                                EvidenceControlLink.organization_id == org_id,
                                EvidenceControlLink.control_id.in_(control_ids),
                                EvidenceControlLink.link_status == "active",
                                EvidenceItem.organization_id == org_id,
                                EvidenceItem.status == "active",
                                EvidenceItem.review_status == "verified",
                                ((EvidenceItem.valid_until.is_(None)) | (EvidenceItem.valid_until > now)),
                            )
                        ).scalar_one()
                    )

                state = states.get(obligation.id)
                readiness = SOC2ReadinessReportBuilder._state_to_readiness(
                    state.implementation_status if state else None,
                    controls_linked,
                )
                if readiness == "ready":
                    ready += 1
                elif readiness == "partial":
                    partial += 1
                else:
                    not_ready += 1

                criteria.append(
                    {
                        "ref": obligation.reference_code,
                        "title": obligation.title,
                        "readiness": readiness,
                        "controls_linked": controls_linked,
                        "evidence_count": evidence_count,
                    }
                )

            if not matching:
                continue

            categories.append(
                {
                    "code": code,
                    "name": name,
                    "total_criteria": len(criteria),
                    "ready": ready,
                    "partial": partial,
                    "not_ready": not_ready,
                    "criteria": criteria,
                }
            )

            summary_total += len(criteria)
            summary_ready += ready
            summary_partial += partial
            summary_not_ready += not_ready

        readiness_pct = round((summary_ready / summary_total) * 100.0, 2) if summary_total else 0.0
        return {
            "report_type": "soc2_readiness",
            "framework": framework.name,
            "categories": categories,
            "summary": {
                "total_criteria": summary_total,
                "ready": summary_ready,
                "partial": summary_partial,
                "not_ready": summary_not_ready,
                "readiness_pct": readiness_pct,
            },
        }


REGULATORY_REPORT_REGISTRY[SOC2ReadinessReportBuilder.report_type] = SOC2ReadinessReportBuilder
