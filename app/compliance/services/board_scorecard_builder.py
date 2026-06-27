import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_deadline import ComplianceDeadline
from app.models.issue import Issue
from app.models.organization_obligation_state import OrganizationObligationState
from app.models.risk import Risk
from app.models.score_snapshot import ScoreSnapshot
from app.models.user import User


OPEN_RISK_STATUSES = ("identified", "assessing", "treatment_planned", "in_treatment", "monitored")


class BoardScorecardBuilder:
    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _today() -> date:
        return datetime.now(UTC).date()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _latest_snapshot(self, org_id: uuid.UUID, db: Session) -> ScoreSnapshot | None:
        return db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.organization_id == org_id)
            .order_by(
                case((ScoreSnapshot.snapshot_type == "compliance_readiness", 1), else_=0).desc(),
                ScoreSnapshot.calculated_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()

    def _closest_snapshot_to_90d(self, org_id: uuid.UUID, db: Session, target: datetime) -> ScoreSnapshot | None:
        rows = db.execute(
            select(ScoreSnapshot).where(ScoreSnapshot.organization_id == org_id)
        ).scalars().all()
        if not rows:
            return None
        closest = min(rows, key=lambda row: abs((self._as_utc(row.calculated_at) - target).total_seconds()))
        if abs((self._as_utc(closest.calculated_at) - target).total_seconds()) > timedelta(days=30).total_seconds():
            return None
        return closest

    def build(self, org_id: uuid.UUID, db: Session) -> dict:
        now = self._now()
        today = self._today()

        latest_snapshot = self._latest_snapshot(org_id, db)
        score = int(latest_snapshot.score) if latest_snapshot is not None else 0

        snapshot_90d = self._closest_snapshot_to_90d(org_id, db, now - timedelta(days=90))
        score_delta = None
        if snapshot_90d is not None:
            score_delta = int(score - snapshot_90d.score)

        top_risk_rows = db.execute(
            select(Risk, User)
            .outerjoin(User, User.id == Risk.owner_user_id)
            .where(
                Risk.organization_id == org_id,
                Risk.status.in_(OPEN_RISK_STATUSES),
            )
            .order_by(
                case(
                    (Risk.severity == "critical", 4),
                    (Risk.severity == "high", 3),
                    (Risk.severity == "medium", 2),
                    else_=1,
                ).desc(),
                Risk.inherent_score.desc(),
                Risk.created_at.desc(),
            )
            .limit(3)
        ).all()
        top_risks = [
            {
                "id": str(risk.id),
                "title": risk.title,
                "severity": risk.severity,
                "owner_name": (owner.full_name if owner and owner.full_name else (owner.email if owner else "Unassigned")),
            }
            for risk, owner in top_risk_rows
        ]

        critical_issues_count = int(
            db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.severity == "critical",
                    Issue.status.notin_(["resolved", "closed"]),
                    Issue.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        active_count = int(
            db.execute(
                select(func.count(ComplianceCertification.id)).where(
                    ComplianceCertification.organization_id == org_id,
                    ComplianceCertification.status == "active",
                    ComplianceCertification.valid_until.is_not(None),
                    ComplianceCertification.valid_until > today,
                    ComplianceCertification.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        expiring_count = int(
            db.execute(
                select(func.count(ComplianceCertification.id)).where(
                    ComplianceCertification.organization_id == org_id,
                    ComplianceCertification.status == "active",
                    ComplianceCertification.valid_until.is_not(None),
                    ComplianceCertification.valid_until > today,
                    ComplianceCertification.valid_until <= (today + timedelta(days=90)),
                    ComplianceCertification.deleted_at.is_(None),
                )
            ).scalar_one()
        )
        expired_count = int(
            db.execute(
                select(func.count(ComplianceCertification.id)).where(
                    ComplianceCertification.organization_id == org_id,
                    ComplianceCertification.deleted_at.is_(None),
                    (
                        (ComplianceCertification.status == "expired")
                        | (ComplianceCertification.valid_until.is_not(None) & (ComplianceCertification.valid_until < today))
                    ),
                )
            ).scalar_one()
        )

        deadline_rows = db.execute(
            select(ComplianceDeadline)
            .where(
                ComplianceDeadline.organization_id == org_id,
                ComplianceDeadline.due_date <= (today + timedelta(days=90)),
                ComplianceDeadline.status.notin_(["completed", "cancelled"]),
            )
            .order_by(ComplianceDeadline.due_date.asc())
            .limit(10)
        ).scalars().all()
        deadline_list = [
            {"title": row.title, "due_date": row.due_date.isoformat(), "status": row.status}
            for row in deadline_rows
        ]

        key_wins_count = int(
            db.execute(
                select(func.count(OrganizationObligationState.id)).where(
                    OrganizationObligationState.organization_id == org_id,
                    OrganizationObligationState.implementation_status == "implemented",
                    OrganizationObligationState.updated_at >= (now - timedelta(days=30)),
                )
            ).scalar_one()
        )

        score_text = f"Your compliance score is {score}%"
        if score_delta is not None:
            delta_sign = "+" if score_delta >= 0 else ""
            score_text += f" ({delta_sign}{score_delta} vs last quarter)"

        if len(top_risks) > 0:
            risk_text = (
                f"You have {critical_issues_count} critical open issue(s) and {len(top_risks)} "
                "high-priority risk(s) requiring attention."
            )
        else:
            risk_text = "No critical risks currently open."

        narrative = (
            f"{score_text}. {risk_text} "
            f"{key_wins_count} obligation(s) newly covered in the past 30 days."
        )

        return {
            "report_type": "board_scorecard",
            "score": score,
            "score_delta": score_delta,
            "narrative": narrative,
            "risks_summary": top_risks,
            "issues_summary": {
                "critical_open_count": critical_issues_count,
            },
            "certifications": {
                "active": active_count,
                "expiring_in_90_days": expiring_count,
                "expired": expired_count,
            },
            "upcoming_deadlines": deadline_list,
            "coverage_improvements": {
                "obligations_met_last_30_days": key_wins_count,
            },
        }
