import uuid

from sqlalchemy.orm import Session

from app.compliance.services.executive_narrative_builder import ExecutiveNarrativeBuilder
from app.models.compliance_report import ComplianceReport
from app.services.report_service import ReportService


class ExecutiveNarrativeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_executive_narrative(self, org_id: uuid.UUID, created_by: uuid.UUID) -> ComplianceReport:
        payload = ExecutiveNarrativeBuilder().build(org_id, self.db)
        report_service = ReportService(self.db)
        sections_payload = payload["sections"]

        sections = [
            report_service._section(
                key="where_we_stand",
                title="Where We Stand",
                body=sections_payload["where_we_stand"],
                data={"where_we_stand": sections_payload["where_we_stand"]},
                provenance={"source_models": ["score_snapshots", "frameworks", "controls", "control_obligation_mappings", "obligations"]},
                sort_order=1,
            ),
            report_service._section(
                key="needs_attention",
                title="Needs Attention",
                body=sections_payload["needs_attention"],
                data={"needs_attention": sections_payload["needs_attention"]},
                provenance={"source_models": ["risks", "issues"]},
                sort_order=2,
            ),
            report_service._section(
                key="achievements_this_quarter",
                title="Achievements This Quarter",
                body=sections_payload["achievements_this_quarter"],
                data={"achievements_this_quarter": sections_payload["achievements_this_quarter"]},
                provenance={"source_models": ["compliance_certifications", "risks"]},
                sort_order=3,
            ),
            report_service._section(
                key="upcoming",
                title="Upcoming",
                body=sections_payload["upcoming"],
                data={"upcoming": sections_payload["upcoming"]},
                provenance={"source_models": ["compliance_deadlines"]},
                sort_order=4,
            ),
            report_service._section(
                key="caveats",
                title="Caveats",
                body=payload["caveat"],
                data={"caveat": payload["caveat"]},
                provenance={"source_models": []},
                sort_order=99,
            ),
        ]
        provenance = {
            "generated_at": report_service.now().isoformat(),
            "generated_by_user_id": str(created_by),
            "organization_id": str(org_id),
            "report_type": "executive_narrative",
        }

        report, _ = report_service.persist_report(
            organization_id=org_id,
            report_type="executive_narrative",
            title="Executive Narrative",
            description="Executive stakeholder compliance narrative report.",
            framework_id=None,
            period_start=None,
            period_end=None,
            generated_by_user_id=created_by,
            sections=sections,
            inputs_summary=payload,
            provenance=provenance,
        )
        return report
