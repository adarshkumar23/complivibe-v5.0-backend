import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.control import Control
from app.models.control_obligation_mapping import ControlObligationMapping
from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.models.evidence_control_link import EvidenceControlLink
from app.models.evidence_item import EvidenceItem
from app.models.membership import Membership
from app.models.user import User
from app.core.validation import validate_choice

ALLOWED_TEST_TYPES = {"manual_attestation", "internal_metadata_check", "evidence_review_check"}
ALLOWED_CHECK_KEYS = {
    "manual_attestation",
    "control_status_implemented",
    "has_verified_current_evidence",
    "has_any_active_evidence",
    "no_expired_verified_evidence",
    "has_active_obligation_mapping",
}
ALLOWED_RESULTS = {"passed", "failed", "needs_review", "not_applicable"}
ALLOWED_CADENCE = {"none", "weekly", "monthly", "quarterly", "annual"}


class ControlTestService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _to_utc(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)

    @classmethod
    def validate_test_type_and_check_key(cls, test_type: str, check_key: str) -> None:
        test_type = validate_choice(test_type, ALLOWED_TEST_TYPES, "test_type", status_code=status.HTTP_400_BAD_REQUEST)
        check_key = validate_choice(check_key, ALLOWED_CHECK_KEYS, "check_key", status_code=status.HTTP_400_BAD_REQUEST)
        if test_type == "manual_attestation" and check_key != "manual_attestation":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="manual_attestation tests must use check_key=manual_attestation",
            )

    @classmethod
    def validate_cadence(cls, cadence: str) -> None:
        cadence = validate_choice(cadence, ALLOWED_CADENCE, "cadence", status_code=status.HTTP_400_BAD_REQUEST)
    def require_control_in_org(self, organization_id: uuid.UUID, control_id: uuid.UUID) -> Control:
        control = self.db.execute(
            select(Control).where(
                Control.id == control_id,
                Control.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if control is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Control not found")
        return control

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
        user = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )

    def require_evidence_in_org(self, organization_id: uuid.UUID, evidence_item_id: uuid.UUID | None) -> None:
        if evidence_item_id is None:
            return
        evidence = self.db.execute(
            select(EvidenceItem).where(
                EvidenceItem.id == evidence_item_id,
                EvidenceItem.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if evidence is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence not found")

    @classmethod
    def calculate_next_due_at(cls, cadence: str, *, from_time: datetime | None = None) -> datetime | None:
        if cadence == "none":
            return None
        base = cls._to_utc(from_time) or cls.now()
        if cadence == "weekly":
            return base + timedelta(days=7)
        if cadence == "monthly":
            return base + timedelta(days=30)
        if cadence == "quarterly":
            return base + timedelta(days=90)
        if cadence == "annual":
            return base + timedelta(days=365)
        return None

    def evaluate_internal_check(
        self,
        *,
        organization_id: uuid.UUID,
        control: Control,
        check_key: str,
        evidence_item_id: uuid.UUID | None,
    ) -> tuple[str, str]:
        if check_key == "control_status_implemented":
            if control.status == "implemented":
                return "passed", "Control status is implemented"
            return "failed", f"Control status is {control.status}"

        if check_key == "has_verified_current_evidence":
            has_row = self.db.execute(
                select(func.count(EvidenceControlLink.id))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.control_id == control.id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.review_status == "verified",
                    EvidenceItem.freshness_status.in_(["current", "expiring_soon"]),
                )
            ).scalar_one()
            if int(has_row) > 0:
                return "passed", "Control has verified current evidence"
            return "failed", "No verified current evidence linked to control"

        if check_key == "has_any_active_evidence":
            has_row = self.db.execute(
                select(func.count(EvidenceControlLink.id))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.control_id == control.id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                )
            ).scalar_one()
            if int(has_row) > 0:
                return "passed", "Control has active linked evidence"
            return "failed", "Control has no active linked evidence"

        if check_key == "no_expired_verified_evidence":
            expired_verified = self.db.execute(
                select(func.count(EvidenceControlLink.id))
                .join(EvidenceItem, EvidenceItem.id == EvidenceControlLink.evidence_item_id)
                .where(
                    EvidenceControlLink.organization_id == organization_id,
                    EvidenceControlLink.control_id == control.id,
                    EvidenceControlLink.link_status == "active",
                    EvidenceItem.organization_id == organization_id,
                    EvidenceItem.status == "active",
                    EvidenceItem.review_status == "verified",
                    EvidenceItem.freshness_status == "expired",
                )
            ).scalar_one()
            if int(expired_verified) > 0:
                return "failed", "Control has expired verified evidence"
            return "passed", "No expired verified evidence linked to control"

        if check_key == "has_active_obligation_mapping":
            mapping_count = self.db.execute(
                select(func.count(ControlObligationMapping.id)).where(
                    ControlObligationMapping.organization_id == organization_id,
                    ControlObligationMapping.control_id == control.id,
                    ControlObligationMapping.status == "active",
                )
            ).scalar_one()
            if int(mapping_count) > 0:
                return "passed", "Control has active obligation mapping"
            return "failed", "Control has no active obligation mapping"

        if check_key == "manual_attestation":
            return "needs_review", "Manual attestation requires manual_result"

        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported check_key")

    def run_summary(self, organization_id: uuid.UUID) -> dict[str, int]:
        now = self.now()

        active_tests = int(
            self.db.execute(
                select(func.count(ControlTestDefinition.id)).where(
                    ControlTestDefinition.organization_id == organization_id,
                    ControlTestDefinition.status == "active",
                )
            ).scalar_one()
        )

        tests_due = int(
            self.db.execute(
                select(func.count(ControlTestDefinition.id)).where(
                    ControlTestDefinition.organization_id == organization_id,
                    ControlTestDefinition.status == "active",
                    ControlTestDefinition.next_due_at.is_not(None),
                    ControlTestDefinition.next_due_at <= now,
                )
            ).scalar_one()
        )

        tests_overdue = int(
            self.db.execute(
                select(func.count(ControlTestDefinition.id)).where(
                    ControlTestDefinition.organization_id == organization_id,
                    ControlTestDefinition.status == "active",
                    ControlTestDefinition.next_due_at.is_not(None),
                    ControlTestDefinition.next_due_at < now,
                )
            ).scalar_one()
        )

        latest_runs = self.db.execute(
            select(ControlTestRun)
            .where(ControlTestRun.organization_id == organization_id)
            .order_by(ControlTestRun.created_at.desc())
        ).scalars().all()

        latest_per_test: dict[uuid.UUID, ControlTestRun] = {}
        for run in latest_runs:
            if run.control_test_definition_id not in latest_per_test:
                latest_per_test[run.control_test_definition_id] = run

        latest_passed = sum(1 for r in latest_per_test.values() if r.result == "passed")
        latest_failed = sum(1 for r in latest_per_test.values() if r.result == "failed")
        latest_needs_review = sum(1 for r in latest_per_test.values() if r.result == "needs_review")

        active_controls = int(
            self.db.execute(
                select(func.count(Control.id)).where(
                    Control.organization_id == organization_id,
                    Control.status != "archived",
                )
            ).scalar_one()
        )
        controls_with_active_tests = int(
            self.db.execute(
                select(func.count(func.distinct(ControlTestDefinition.control_id))).where(
                    ControlTestDefinition.organization_id == organization_id,
                    ControlTestDefinition.status == "active",
                )
            ).scalar_one()
        )

        return {
            "active_tests": active_tests,
            "tests_due": tests_due,
            "tests_overdue": tests_overdue,
            "latest_passed": latest_passed,
            "latest_failed": latest_failed,
            "latest_needs_review": latest_needs_review,
            "controls_without_tests": max(0, active_controls - controls_with_active_tests),
        }
