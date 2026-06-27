import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.compliance.services.eu_ai_act_builder import EUAIActConformityBuilder  # noqa: F401
from app.compliance.services.gdpr_ropa_builder import GDPRArticle30Builder  # noqa: F401
from app.compliance.services.iso27001_soa_builder import ISO27001SOABuilder  # noqa: F401
from app.compliance.services.nist_ai_rmf_builder import NISTAIRMFSummaryBuilder  # noqa: F401
from app.compliance.services.regulatory_report_registry import REGULATORY_REPORT_DESCRIPTIONS, REGULATORY_REPORT_REGISTRY
from app.compliance.services.soc2_readiness_builder import SOC2ReadinessReportBuilder  # noqa: F401
from app.models.compliance_report import ComplianceReport
from app.services.report_service import REPORT_CAVEAT, ReportService


class RegulatoryReportService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_regulatory_report(
        self,
        org_id: uuid.UUID,
        report_type: str,
        db: Session,
        created_by: uuid.UUID,
    ) -> ComplianceReport:
        _ = db
        builder = REGULATORY_REPORT_REGISTRY.get(report_type)
        if builder is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown regulatory report type.")

        payload = builder.build(org_id, self.db)
        report_service = ReportService(self.db)
        sections = [
            report_service._section(
                key=report_type,
                title=report_type.replace("_", " ").title(),
                body=payload.get("message") or f"Generated {report_type} report.",
                data=payload,
                provenance={"source_models": ["frameworks", "obligations", "organization_obligation_states", "controls", "evidence_items"]},
                sort_order=1,
            ),
            report_service._section(
                key="caveats",
                title="Caveats",
                body=REPORT_CAVEAT,
                data={"caveat": REPORT_CAVEAT},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        report, _rows = report_service.persist_report(
            organization_id=org_id,
            report_type=report_type,
            title=report_type.replace("_", " ").title(),
            description=f"Regulatory report: {report_type}",
            framework_id=None,
            period_start=None,
            period_end=None,
            generated_by_user_id=created_by,
            sections=sections,
            inputs_summary=payload,
            provenance={
                "generated_by_user_id": str(created_by),
                "organization_id": str(org_id),
                "report_type": report_type,
            },
        )
        return report

    @staticmethod
    def list_available_report_types() -> list[dict]:
        return [
            {"report_type": key, "description": REGULATORY_REPORT_DESCRIPTIONS.get(key, "")}
            for key in sorted(REGULATORY_REPORT_REGISTRY.keys())
        ]
