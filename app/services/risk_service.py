import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.risk_appetite_service import RiskAppetiteService
from app.models.control import Control
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.risk import Risk
from app.models.risk_control_link import RiskControlLink


class RiskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def ensure_score_value(value: int | None, field_name: str) -> None:
        if value is None:
            return
        if value < 1 or value > 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} must be between 1 and 5")

    @classmethod
    def score_to_severity(cls, score: int) -> str:
        if score <= 4:
            return "low"
        if score <= 9:
            return "medium"
        if score <= 16:
            return "high"
        return "critical"

    @classmethod
    def calculate_scores(
        cls,
        *,
        likelihood: int,
        impact: int,
        residual_likelihood: int | None,
        residual_impact: int | None,
    ) -> tuple[int, str, int | None]:
        cls.ensure_score_value(likelihood, "likelihood")
        cls.ensure_score_value(impact, "impact")
        cls.ensure_score_value(residual_likelihood, "residual_likelihood")
        cls.ensure_score_value(residual_impact, "residual_impact")

        inherent_score = likelihood * impact
        severity = cls.score_to_severity(inherent_score)

        residual_score: int | None = None
        if residual_likelihood is not None and residual_impact is not None:
            residual_score = residual_likelihood * residual_impact

        return inherent_score, severity, residual_score

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID | None) -> None:
        if owner_user_id is None:
            return

        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

    def check_appetite_breach(self, *, organization_id: uuid.UUID, risk: Risk, actor_user_id: uuid.UUID | None = None) -> None:
        RiskAppetiteService(self.db).check_appetite_breach(
            org_id=organization_id,
            risk_id=risk.id,
            new_score=risk.inherent_score,
            risk_category=risk.category,
            actor_user_id=actor_user_id,
        )

    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(Control.id == control_id, Control.organization_id == organization_id)
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

    def require_evidence_in_org(self, organization_id: uuid.UUID, evidence_item_id: uuid.UUID) -> EvidenceItem:
        evidence = self.db.execute(
            select(EvidenceItem).where(EvidenceItem.id == evidence_item_id, EvidenceItem.organization_id == organization_id)
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")
        return evidence

    def summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        total_risks = int(self.db.execute(select(func.count(Risk.id)).where(Risk.organization_id == organization_id)).scalar_one())
        open_risks = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.status.in_(["identified", "assessing", "treatment_planned", "in_treatment", "monitored"]),
                )
            ).scalar_one()
        )
        accepted_risks = int(
            self.db.execute(select(func.count(Risk.id)).where(Risk.organization_id == organization_id, Risk.status == "accepted")).scalar_one()
        )
        mitigated_risks = int(
            self.db.execute(select(func.count(Risk.id)).where(Risk.organization_id == organization_id, Risk.status == "mitigated")).scalar_one()
        )

        severity_counts = {}
        for level in ["critical", "high", "medium", "low"]:
            severity_counts[level] = int(
                self.db.execute(
                    select(func.count(Risk.id)).where(
                        Risk.organization_id == organization_id,
                        Risk.severity == level,
                        Risk.status != "archived",
                    )
                ).scalar_one()
            )

        risks_with_controls = int(
            self.db.execute(
                select(func.count(func.distinct(RiskControlLink.risk_id))).where(
                    RiskControlLink.organization_id == organization_id,
                    RiskControlLink.status == "active",
                )
            ).scalar_one()
        )
        risks_without_owner = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.owner_user_id.is_(None),
                    Risk.status != "archived",
                )
            ).scalar_one()
        )

        now = datetime.now(UTC)
        overdue_risk_reviews = int(
            self.db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == organization_id,
                    Risk.review_due_at.is_not(None),
                    Risk.review_due_at < now,
                    Risk.status != "archived",
                )
            ).scalar_one()
        )

        return {
            "total_risks": total_risks,
            "open_risks": open_risks,
            "accepted_risks": accepted_risks,
            "mitigated_risks": mitigated_risks,
            "critical_risks": severity_counts["critical"],
            "high_risks": severity_counts["high"],
            "medium_risks": severity_counts["medium"],
            "low_risks": severity_counts["low"],
            "risks_without_controls": max(0, total_risks - risks_with_controls),
            "risks_without_owner": risks_without_owner,
            "overdue_risk_reviews": overdue_risk_reviews,
        }

    def heatmap(self, organization_id: uuid.UUID) -> list[dict]:
        rows = self.db.execute(
            select(Risk)
            .where(Risk.organization_id == organization_id, Risk.status != "archived")
            .order_by(Risk.created_at.desc())
        ).scalars().all()

        matrix: dict[tuple[int, int], dict] = {}
        for likelihood in range(1, 6):
            for impact in range(1, 6):
                matrix[(likelihood, impact)] = {
                    "likelihood": likelihood,
                    "impact": impact,
                    "count": 0,
                    "risks": [],
                }

        for risk in rows:
            key = (risk.likelihood, risk.impact)
            cell = matrix[key]
            cell["count"] += 1
            cell["risks"].append({"id": str(risk.id), "title": risk.title})

        return [matrix[(l, i)] for l in range(1, 6) for i in range(1, 6)]
