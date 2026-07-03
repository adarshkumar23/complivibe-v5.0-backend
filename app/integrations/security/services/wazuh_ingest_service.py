from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.security.parsers.wazuh_parser import WazuhParser
from app.integrations.security.services.base_service import SecurityIngestBaseService
from app.models.security_scan_job import SecurityScanJob
from app.services.audit_service import AuditService


class WazuhIngestService:
    def process(self, org_id: uuid.UUID, payload: list | dict, db: Session) -> dict:
        if not isinstance(payload, (list, dict)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Wazuh payload")

        base = SecurityIngestBaseService(db)

        job = SecurityScanJob(
            organization_id=org_id,
            scan_source="wazuh",
            scan_type="siem_alert",
            status="processing",
            source_metadata={},
        )
        db.add(job)
        db.flush()

        parser = WazuhParser()
        findings = parser.parse(payload)

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        issues_created = 0
        control_tests = 0

        try:
            for finding in findings:
                sev = finding["severity"]
                counts[sev] = counts.get(sev, 0) + 1

                finding["resolved_framework_refs"] = base.resolve_framework_refs(finding.get("framework_refs", []))
                base.create_control_test_result(
                    org_id=org_id,
                    check_key=f"wazuh_{finding['rule_id']}_{finding['agent_name']}",
                    check_type="siem_alert",
                    result="fail",
                    severity=sev,
                    detail=finding,
                    source="wazuh",
                )
                control_tests += 1

                if sev in ("critical", "high"):
                    base.create_issue(
                        org_id=org_id,
                        title=f"Wazuh Alert (Level {finding['level']}): {finding['rule_description'][:150]}",
                        description=(
                            "Wazuh security alert.\n"
                            f"Rule ID: {finding['rule_id']}\n"
                            f"Agent: {finding['agent_name']} ({finding['agent_ip']})\n"
                            f"Level: {finding['level']}\n"
                            f"Timestamp: {finding['timestamp']}"
                        ),
                        severity=sev,
                    )
                    issues_created += 1

            job.status = "completed"
            job.completed_at = datetime.now(UTC)
            job.total_findings = len(findings)
            job.critical_count = counts.get("critical", 0)
            job.high_count = counts.get("high", 0)
            job.medium_count = counts.get("medium", 0)
            job.low_count = counts.get("low", 0)
            job.issues_created = issues_created
            job.control_tests_created = control_tests
            db.flush()
        except Exception as exc:
            job.status = "failed"
            job.error_message = str(exc)[:1000]
            job.completed_at = datetime.now(UTC)
            db.flush()
            raise

        AuditService(db).write_audit_log(
            action="security.wazuh_alerts_ingested",
            entity_type="security_scan_jobs",
            organization_id=org_id,
            entity_id=job.id,
            metadata_json={
                "alert_count": len(findings),
                "issues_created": issues_created,
            },
        )

        return {
            "scan_job_id": str(job.id),
            "scan_source": "wazuh",
            "total_alerts": len(findings),
            "critical_count": counts.get("critical", 0),
            "high_count": counts.get("high", 0),
            "medium_count": counts.get("medium", 0),
            "low_count": counts.get("low", 0),
            "issues_created": issues_created,
            "control_tests_created": control_tests,
        }
