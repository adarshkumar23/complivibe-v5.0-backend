import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.obligation import Obligation
from app.models.organization_framework import OrganizationFramework
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.vendor import Vendor
from app.schemas.dashboard import DashboardSummary
from app.services.compliance_dashboard_service import ComplianceDashboardService
from app.services.risk_service import RiskService
from app.services.task_service import TaskService


class DashboardService:
    """Computes the org-wide top-level dashboard summary.

    This mirrors (and intentionally reuses) the same org-scoped, live query
    logic that backs ``/compliance/dashboard/posture-summary`` so the two
    endpoints never disagree about the same numbers for the same org. Before
    this fix, every field here was a hardcoded default (0 / None) regardless
    of the org or its real data -- see git history: this file and its router
    were never implemented past initial scaffolding.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_summary(self, organization_id: uuid.UUID) -> DashboardSummary:
        open_obligations = int(
            self.db.execute(
                select(func.count(func.distinct(OrganizationObligationState.obligation_id)))
                .join(Obligation, Obligation.id == OrganizationObligationState.obligation_id)
                .join(OrganizationFramework, OrganizationFramework.framework_id == Obligation.framework_id)
                .where(
                    OrganizationObligationState.organization_id == organization_id,
                    OrganizationFramework.organization_id == organization_id,
                    OrganizationFramework.status == "active",
                    Obligation.status == "active",
                    OrganizationObligationState.applicability_status == "applicable",
                    OrganizationObligationState.implementation_status != "implemented",
                )
            ).scalar_one()
        )

        risk_summary = RiskService(self.db).summary(organization_id)
        open_risks = int(risk_summary["open_risks"])

        task_summary = TaskService(self.db).summary(organization_id)
        pending_tasks = (
            int(task_summary["open_tasks"])
            + int(task_summary["in_progress_tasks"])
            + int(task_summary["blocked_tasks"])
        )

        score_snapshot = ComplianceDashboardService(self.db)._latest_score_snapshot(organization_id)
        current_score = int(score_snapshot["score"]) if score_snapshot and score_snapshot["score"] is not None else None
        current_score_grade = score_snapshot["grade"] if score_snapshot else None
        current_score_calculated_at = score_snapshot["calculated_at"] if score_snapshot else None

        # NOTE: matches ComplianceDashboardService.posture_summary()'s
        # controls.total / vendors.total, which count every row for the org
        # regardless of archive status. Filtering out archived rows here
        # (as an earlier version did) made this endpoint silently undercount
        # vs. posture-summary and vs. a direct DB count for the same org.
        total_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                )
            ).scalar_one()
        )
        total_vendors = int(
            self.db.execute(
                select(func.count(Vendor.id)).where(
                    Vendor.organization_id == organization_id,
                )
            ).scalar_one()
        )
        total_policies = int(
            self.db.execute(
                select(func.count(CompliancePolicy.id)).where(
                    CompliancePolicy.organization_id == organization_id,
                )
            ).scalar_one()
        )

        return DashboardSummary(
            open_obligations=open_obligations,
            open_risks=open_risks,
            pending_tasks=pending_tasks,
            current_score=current_score,
            current_score_grade=current_score_grade,
            current_score_calculated_at=current_score_calculated_at,
            total_controls=total_controls,
            total_vendors=total_vendors,
            total_policies=total_policies,
        )
