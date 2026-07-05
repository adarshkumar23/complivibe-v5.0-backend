"""DORA digital operational resilience testing service.

Cadence rules (grounded, not re-derived here):

- Regulation (EU) 2022/2554 (DORA), Article 24: financial entities (other
  than microenterprises) must test all ICT systems and tools that support
  critical or important functions **at least yearly** as part of a
  documented digital operational resilience testing programme. Applied here
  to the ``tabletop`` and ``simulation`` test types.
- Regulation (EU) 2022/2554 (DORA), Article 26, and the Joint RTS on
  Threat-Led Penetration Testing (Commission Delegated Regulation (EU)
  2025/1190, applicable from 8 July 2025): in-scope entities must run
  Threat-Led Penetration Testing (TLPT) **at least every 3 years**. Applied
  here to the ``threat_led_pen_test`` test type.

An organization that has never run a given test type is treated as
immediately overdue for it -- "never tested" is the most overdue state,
not an absence of data to be silently skipped.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compliance.services.issue_service import IssueService
from app.models.issue import Issue
from app.models.resilience_testing import ResilienceTest
from app.schemas.issue import IssueCreate
from app.services.audit_service import AuditService

_YEARLY_CADENCE_DAYS = 365
_TLPT_CADENCE_DAYS = 365 * 3  # 1095 days

_HIGH_SEVERITY_ISSUE_THRESHOLD = ("critical", "high")

_TEST_TYPES = ("tabletop", "simulation", "threat_led_pen_test")

_TEST_TYPE_LABELS = {
    "tabletop": "Tabletop exercise",
    "simulation": "Simulation test",
    "threat_led_pen_test": "Threat-Led Penetration Test (TLPT)",
}


def _cadence_days(test_type: str) -> int:
    return _TLPT_CADENCE_DAYS if test_type == "threat_led_pen_test" else _YEARLY_CADENCE_DAYS


def _cadence_citation(test_type: str) -> str:
    if test_type == "threat_led_pen_test":
        return (
            "Regulation (EU) 2022/2554 (DORA), Article 26; Joint RTS on Threat-Led "
            "Penetration Testing, Commission Delegated Regulation (EU) 2025/1190 "
            "(at least every 3 years)"
        )
    return "Regulation (EU) 2022/2554 (DORA), Article 24 (at least yearly)"


class ResilienceTestingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create_test(
        self,
        *,
        organization_id: uuid.UUID,
        test_type: str,
        scope: str,
        scheduled_date: date,
        owner_team: str | None,
        created_by_user_id: uuid.UUID | None,
    ) -> ResilienceTest:
        test = ResilienceTest(
            organization_id=organization_id,
            test_type=test_type,
            scope=scope,
            scheduled_date=scheduled_date,
            owner_team=owner_team,
            created_by_user_id=created_by_user_id,
            status="scheduled",
            findings_count=0,
        )
        self.db.add(test)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="resilience_test.created",
            entity_type="resilience_test",
            entity_id=test.id,
            organization_id=organization_id,
            actor_user_id=created_by_user_id,
            after_json={"test_type": test_type, "scheduled_date": scheduled_date.isoformat(), "status": test.status},
        )
        return test

    def get_test(self, organization_id: uuid.UUID, test_id: uuid.UUID) -> ResilienceTest:
        test = self.db.execute(
            select(ResilienceTest).where(
                ResilienceTest.id == test_id,
                ResilienceTest.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if test is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resilience test not found")
        return test

    def list_tests(self, organization_id: uuid.UUID) -> list[ResilienceTest]:
        return list(
            self.db.execute(
                select(ResilienceTest)
                .where(ResilienceTest.organization_id == organization_id)
                .order_by(ResilienceTest.scheduled_date.desc())
            ).scalars()
        )

    def update_test(
        self,
        *,
        organization_id: uuid.UUID,
        test_id: uuid.UUID,
        scope: str | None,
        scheduled_date: date | None,
        owner_team: str | None,
        status_value: str | None,
        actor_user_id: uuid.UUID | None,
    ) -> ResilienceTest:
        test = self.get_test(organization_id, test_id)
        before = {"scope": test.scope, "scheduled_date": test.scheduled_date.isoformat(), "status": test.status}

        if scope is not None:
            test.scope = scope
        if scheduled_date is not None:
            test.scheduled_date = scheduled_date
        if owner_team is not None:
            test.owner_team = owner_team
        if status_value is not None:
            test.status = status_value

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="resilience_test.updated",
            entity_type="resilience_test",
            entity_id=test.id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"scope": test.scope, "scheduled_date": test.scheduled_date.isoformat(), "status": test.status},
        )
        return test

    # ------------------------------------------------------------------
    # Completion + auto issue creation
    # ------------------------------------------------------------------
    def complete_test(
        self,
        *,
        organization_id: uuid.UUID,
        test_id: uuid.UUID,
        completed_by_user_id: uuid.UUID,
        results: dict[str, Any],
        issue_severity_threshold: tuple[str, ...] = _HIGH_SEVERITY_ISSUE_THRESHOLD,
    ) -> tuple[ResilienceTest, list[uuid.UUID]]:
        test = self.get_test(organization_id, test_id)

        if test.status == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot complete a cancelled resilience test",
            )
        if test.status == "completed":
            # Idempotent re-completion: refresh results/findings but never
            # duplicate the auto-created issues (checked below by source_id).
            pass

        findings = results.get("findings", []) or []
        if not isinstance(findings, list):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="'findings' must be a list")

        test.status = "completed"
        test.completed_date = date.today()
        test.results_json = results
        test.findings_count = len(findings)
        self.db.flush()

        issue_service = IssueService(self.db)
        existing_issue_descriptions = {
            row.description
            for row in self.db.execute(
                select(Issue).where(
                    Issue.organization_id == organization_id,
                    Issue.source_type == "risk_assessment",
                    Issue.source_id == test.id,
                )
            ).scalars()
        }

        issues_created: list[uuid.UUID] = []
        for finding in findings:
            severity = finding.get("severity")
            description_text = finding.get("description", "")
            if severity not in issue_severity_threshold:
                continue

            issue_description = (
                f"Finding from DORA resilience test {test.id} "
                f"({_TEST_TYPE_LABELS.get(test.test_type, test.test_type)}): {description_text}"
            )
            if issue_description in existing_issue_descriptions:
                # Already created on a prior completion of this same test -- skip.
                continue

            issue = issue_service.create_issue(
                organization_id,
                IssueCreate(
                    title=f"Resilience test finding: {description_text[:200]}",
                    description=issue_description,
                    issue_type="operational_failure",
                    severity=severity,
                    source_type="risk_assessment",
                    source_id=test.id,
                    owner_id=completed_by_user_id,
                ),
                completed_by_user_id,
            )
            existing_issue_descriptions.add(issue_description)
            issues_created.append(issue.id)

        AuditService(self.db).write_audit_log(
            action="resilience_test.completed",
            entity_type="resilience_test",
            entity_id=test.id,
            organization_id=organization_id,
            actor_user_id=completed_by_user_id,
            after_json={
                "status": test.status,
                "findings_count": test.findings_count,
                "issues_created": [str(i) for i in issues_created],
            },
        )
        return test, issues_created

    # ------------------------------------------------------------------
    # DORA cadence overdue computation
    # ------------------------------------------------------------------
    def compute_overdue(self, organization_id: uuid.UUID) -> list[dict[str, Any]]:
        today = date.today()
        results: list[dict[str, Any]] = []

        all_tests = self.list_tests(organization_id)

        for test_type in _TEST_TYPES:
            completed_of_type = [
                t for t in all_tests if t.test_type == test_type and t.status == "completed" and t.completed_date is not None
            ]
            last_completed = max(completed_of_type, key=lambda t: t.completed_date, default=None)
            cadence_days = _cadence_days(test_type)
            citation = _cadence_citation(test_type)

            if last_completed is None:
                results.append(
                    {
                        "test_type": test_type,
                        "is_overdue": True,
                        "reason": (
                            f"No completed {_TEST_TYPE_LABELS[test_type]} has ever been recorded for this "
                            f"organization. {citation} -- an organization with no completed test is treated "
                            "as immediately overdue."
                        ),
                        "last_completed_date": None,
                        "next_due_date": today,
                    }
                )
            else:
                days_since = (today - last_completed.completed_date).days
                is_overdue = days_since > cadence_days
                next_due = last_completed.completed_date + timedelta(days=cadence_days)
                reason = (
                    f"Last completed {_TEST_TYPE_LABELS[test_type]} was {days_since} day(s) ago "
                    f"({'exceeds' if is_overdue else 'within'} the {cadence_days}-day cadence limit). {citation}."
                )
                results.append(
                    {
                        "test_type": test_type,
                        "is_overdue": is_overdue,
                        "reason": reason,
                        "last_completed_date": last_completed.completed_date,
                        "next_due_date": next_due,
                    }
                )

        # Separately flag any scheduled-but-missed tests (distinct overdue reason).
        for test in all_tests:
            if test.status == "scheduled" and test.scheduled_date < today:
                days_late = (today - test.scheduled_date).days
                results.append(
                    {
                        "test_type": test.test_type,
                        "is_overdue": True,
                        "reason": (
                            f"Scheduled {_TEST_TYPE_LABELS.get(test.test_type, test.test_type)} "
                            f"(test id {test.id}) was due on {test.scheduled_date.isoformat()} "
                            f"and is {days_late} day(s) overdue with status still 'scheduled'."
                        ),
                        "last_completed_date": None,
                        "next_due_date": test.scheduled_date,
                    }
                )

        return results
