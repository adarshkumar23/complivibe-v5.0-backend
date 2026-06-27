import uuid

from sqlalchemy.orm import Session

from app.compliance.services.board_scorecard_builder import BoardScorecardBuilder
from app.models.compliance_report import ComplianceReport
from app.services.report_service import REPORT_CAVEAT, ReportService


class BoardScorecardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def generate_board_scorecard(self, org_id: uuid.UUID, created_by: uuid.UUID) -> ComplianceReport:
        payload = BoardScorecardBuilder().build(org_id, self.db)
        report_service = ReportService(self.db)

        sections = [
            report_service._section(
                key="board_scorecard",
                title="Board Scorecard",
                body=payload["narrative"],
                data=payload,
                provenance={
                    "source_models": [
                        "score_snapshots",
                        "risks",
                        "issues",
                        "compliance_certifications",
                        "compliance_deadlines",
                        "organization_obligation_states",
                    ]
                },
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
        provenance = {
            "generated_at": report_service.now().isoformat(),
            "generated_by_user_id": str(created_by),
            "organization_id": str(org_id),
            "report_type": "board_scorecard",
        }

        report, _ = report_service.persist_report(
            organization_id=org_id,
            report_type="board_scorecard",
            title="Board Scorecard",
            description="Single-page executive compliance health report for board presentation.",
            framework_id=None,
            period_start=None,
            period_end=None,
            generated_by_user_id=created_by,
            sections=sections,
            inputs_summary=payload,
            provenance=provenance,
        )
        return report
