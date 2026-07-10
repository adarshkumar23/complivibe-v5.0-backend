import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.control_test_definition import ControlTestDefinition
from app.models.control_test_run import ControlTestRun
from app.services.audit_service import AuditService
from app.services.control_test_service import ControlTestService

CRITICAL_SEVERITIES = {"critical", "high"}
CHECK_KEY = "cloud_finding_severity"
TEST_TYPE = "automated_ingest"


class CloudFindingMonitoringService:
    """Wires critical/high-severity findings into the EXISTING control-test/continuous-
    monitoring infrastructure (ControlTestDefinition/ControlTestRun ->
    control_monitoring_alert_service) — not a parallel monitoring system."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _get_or_create_test_definition(self, org_id: uuid.UUID, control_id: uuid.UUID) -> ControlTestDefinition:
        existing = self.db.execute(
            select(ControlTestDefinition).where(
                ControlTestDefinition.organization_id == org_id,
                ControlTestDefinition.control_id == control_id,
                ControlTestDefinition.check_key == CHECK_KEY,
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        now = self.utcnow()
        definition = ControlTestDefinition(
            organization_id=org_id,
            control_id=control_id,
            name="Cloud connector critical/high finding check",
            description="Automatically created when a cloud evidence connector maps a critical/high finding to this control.",
            test_type=TEST_TYPE,
            check_key=CHECK_KEY,
            status="active",
            cadence="none",
            created_at=now,
            updated_at=now,
        )
        self.db.add(definition)
        self.db.flush()
        return definition

    def record_finding_test_run(
        self,
        org_id: uuid.UUID,
        control_id: uuid.UUID,
        evidence_item_id: uuid.UUID,
        severity: str,
        finding_summary: str,
    ) -> ControlTestRun | None:
        if severity not in CRITICAL_SEVERITIES:
            return None

        definition = self._get_or_create_test_definition(org_id, control_id)
        service = ControlTestService(self.db)
        now = service.now()

        run = ControlTestRun(
            organization_id=org_id,
            control_test_definition_id=definition.id,
            control_id=control_id,
            result="failed",
            result_reason=f"Cloud connector reported a {severity}-severity finding: {finding_summary}",
            check_key=CHECK_KEY,
            executed_by_user_id=None,
            execution_source="cloud_connector",
            evidence_item_id=evidence_item_id,
            metadata_json={"test_type": TEST_TYPE, "severity": severity},
            created_at=now,
        )
        self.db.add(run)

        definition.last_run_at = now
        definition.next_due_at = service.calculate_next_due_at(definition.cadence, from_time=now)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="control_test.run_created",
            entity_type="control_test_run",
            entity_id=run.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json={"result": "failed", "control_id": str(control_id), "severity": severity},
            metadata_json={"source": "cloud_connector"},
        )
        return run
