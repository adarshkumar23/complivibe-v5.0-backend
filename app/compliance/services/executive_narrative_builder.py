import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.compliance.templates.executive_narrative_templates import (
    ACHIEVEMENTS,
    CAVEAT,
    ISSUES_ONLY_ATTENTION,
    NEEDS_ATTENTION,
    NO_ACHIEVEMENTS,
    NO_DEADLINES,
    NO_OPEN_RISKS,
    UPCOMING,
    WHERE_WE_STAND,
)
from app.models.compliance_certification import ComplianceCertification
from app.models.compliance_deadline import ComplianceDeadline
from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.framework import Framework
from app.models.issue import Issue
from app.models.obligation import Obligation
from app.models.risk import Risk
from app.models.score_snapshot import ScoreSnapshot

OPEN_RISK_STATUSES = ("identified", "assessing", "treatment_planned", "in_treatment", "monitored")


class ExecutiveNarrativeBuilder:
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

    def _score_and_delta(self, org_id: uuid.UUID, db: Session, now: datetime) -> tuple[int, int | None]:
        latest = db.execute(
            select(ScoreSnapshot)
            .where(ScoreSnapshot.organization_id == org_id)
            .order_by(
                case((ScoreSnapshot.snapshot_type == "compliance_readiness", 1), else_=0).desc(),
                ScoreSnapshot.calculated_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        score = int(latest.score) if latest is not None else 0

        history = db.execute(select(ScoreSnapshot).where(ScoreSnapshot.organization_id == org_id)).scalars().all()
        if not history:
            return score, None
        target = now - timedelta(days=90)
        closest = min(history, key=lambda row: abs((self._as_utc(row.calculated_at) - target).total_seconds()))
        if abs((self._as_utc(closest.calculated_at) - target).total_seconds()) > timedelta(days=30).total_seconds():
            return score, None
        return score, int(score - closest.score)

    def _framework_coverage(self, org_id: uuid.UUID, db: Session) -> tuple[str, int]:
        framework_counts = db.execute(
            select(
                Obligation.framework_id,
                func.count(func.distinct(ControlObligationMapping.control_id)).label("control_count"),
            )
            .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
            .where(
                ControlObligationMapping.organization_id == org_id,
                ControlObligationMapping.status == "active",
            )
            .group_by(Obligation.framework_id)
            .order_by(func.count(func.distinct(ControlObligationMapping.control_id)).desc())
            .limit(1)
        ).first()

        if framework_counts is None:
            return "N/A", 0

        framework_id = framework_counts[0]
        framework = db.execute(select(Framework).where(Framework.id == framework_id)).scalar_one_or_none()
        framework_name = framework.name if framework is not None else "N/A"

        total_controls = int(
            db.execute(
                select(func.count(func.distinct(ControlObligationMapping.control_id)))
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .join(Control, Control.id == ControlObligationMapping.control_id)
                .where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id == framework_id,
                    Control.organization_id == org_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )
        implemented_controls = int(
            db.execute(
                select(func.count(func.distinct(ControlObligationMapping.control_id)))
                .join(Obligation, Obligation.id == ControlObligationMapping.obligation_id)
                .join(Control, Control.id == ControlObligationMapping.control_id)
                .where(
                    ControlObligationMapping.organization_id == org_id,
                    ControlObligationMapping.status == "active",
                    Obligation.framework_id == framework_id,
                    Control.organization_id == org_id,
                    Control.status == "implemented",
                )
            ).scalar_one()
        )
        coverage_pct = int(round((implemented_controls / total_controls) * 100)) if total_controls > 0 else 0
        return framework_name, coverage_pct

    def build(self, org_id: uuid.UUID, db: Session) -> dict:
        now = self._now()
        today = self._today()

        score, score_delta = self._score_and_delta(org_id, db, now)
        framework_name, coverage_pct = self._framework_coverage(org_id, db)

        open_risks = int(
            db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == org_id,
                    Risk.status.in_(OPEN_RISK_STATUSES),
                )
            ).scalar_one()
        )
        top_risk = db.execute(
            select(Risk)
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
                Risk.updated_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()

        critical_issue_count = int(
            db.execute(
                select(func.count(Issue.id)).where(
                    Issue.organization_id == org_id,
                    Issue.severity == "critical",
                    Issue.status.notin_(["resolved", "closed"]),
                    Issue.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        certifications_gained = int(
            db.execute(
                select(func.count(ComplianceCertification.id)).where(
                    ComplianceCertification.organization_id == org_id,
                    ComplianceCertification.status == "active",
                    ComplianceCertification.created_at >= (now - timedelta(days=90)),
                    ComplianceCertification.deleted_at.is_(None),
                )
            ).scalar_one()
        )

        risks_closed = int(
            db.execute(
                select(func.count(Risk.id)).where(
                    Risk.organization_id == org_id,
                    Risk.status == "mitigated",
                    Risk.updated_at >= (now - timedelta(days=90)),
                )
            ).scalar_one()
        )

        deadlines = db.execute(
            select(ComplianceDeadline)
            .where(
                ComplianceDeadline.organization_id == org_id,
                ComplianceDeadline.due_date <= (today + timedelta(days=90)),
                ComplianceDeadline.status.notin_(["completed", "cancelled"]),
            )
            .order_by(ComplianceDeadline.due_date.asc())
        ).scalars().all()

        if score_delta is None:
            delta_clause = ""
        else:
            delta_clause = f" (+{score_delta} vs last quarter)" if score_delta >= 0 else f" ({score_delta} vs last quarter)"

        where_we_stand = WHERE_WE_STAND.format(
            coverage_pct=coverage_pct,
            framework_name=framework_name,
            score=score,
            delta_clause=delta_clause,
        )

        if open_risks == 0 or top_risk is None:
            high_severity_issue_count = int(
                db.execute(
                    select(func.count(Issue.id)).where(
                        Issue.organization_id == org_id,
                        Issue.severity.in_(["critical", "high"]),
                        Issue.status.notin_(["resolved", "closed"]),
                        Issue.deleted_at.is_(None),
                    )
                ).scalar_one()
            )
            if high_severity_issue_count == 0:
                needs_attention = NO_OPEN_RISKS
            else:
                top_issue = db.execute(
                    select(Issue)
                    .where(
                        Issue.organization_id == org_id,
                        Issue.severity.in_(["critical", "high"]),
                        Issue.status.notin_(["resolved", "closed"]),
                        Issue.deleted_at.is_(None),
                    )
                    .order_by(
                        case(
                            (Issue.severity == "critical", 2),
                            (Issue.severity == "high", 1),
                            else_=0,
                        ).desc(),
                        Issue.updated_at.desc(),
                    )
                    .limit(1)
                ).scalar_one()
                needs_attention = ISSUES_ONLY_ATTENTION.format(
                    high_severity_issue_count=high_severity_issue_count,
                    top_issue_title=top_issue.title,
                    top_issue_severity=top_issue.severity,
                )
        else:
            issue_sentence = (
                f" {critical_issue_count} critical issue(s) require immediate attention."
                if critical_issue_count > 0
                else ""
            )
            needs_attention = NEEDS_ATTENTION.format(
                open_risk_count=open_risks,
                top_risk_title=top_risk.title,
                top_risk_severity=top_risk.severity,
                critical_issue_count=critical_issue_count,
            )
            if critical_issue_count == 0:
                needs_attention = needs_attention.replace(
                    f" {critical_issue_count} critical issue(s) require immediate attention.",
                    issue_sentence,
                )

        if certifications_gained == 0 and risks_closed == 0:
            achievements = NO_ACHIEVEMENTS
        else:
            achievements = ACHIEVEMENTS.format(
                certifications_gained=certifications_gained,
                risks_closed=risks_closed,
            )

        if not deadlines:
            upcoming = NO_DEADLINES
        else:
            nearest = deadlines[0]
            upcoming = UPCOMING.format(
                deadline_count=len(deadlines),
                nearest_deadline_title=nearest.title,
                nearest_due_date=nearest.due_date.isoformat(),
            )

        caveat = CAVEAT.format(report_date=today.isoformat())

        return {
            "report_type": "executive_narrative",
            "sections": {
                "where_we_stand": where_we_stand,
                "needs_attention": needs_attention,
                "achievements_this_quarter": achievements,
                "upcoming": upcoming,
            },
            "caveat": caveat,
            "generated_at": now.isoformat(),
            "data_summary": {
                "score": score,
                "framework_name": framework_name,
                "coverage_pct": coverage_pct,
                "open_risk_count": open_risks,
                "critical_issue_count": critical_issue_count,
            },
        }
