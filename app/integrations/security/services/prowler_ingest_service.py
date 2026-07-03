from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.security.parsers.prowler_parser import ProwlerParser
from app.integrations.security.services.base_service import SecurityIngestBaseService
from app.models.security_scan_job import SecurityScanJob
from app.services.audit_service import AuditService


class ProwlerIngestService:
    def process(
        self,
        org_id: uuid.UUID,
        payload: object,
        db: Session,
    ) -> dict:
        if not isinstance(payload, (list, dict)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Prowler payload")

        base = SecurityIngestBaseService(db)
        job = SecurityScanJob(
            organization_id=org_id,
            scan_source="prowler",
            scan_type="infrastructure",
            status="processing",
            source_metadata={},
        )
        db.add(job)
        db.flush()

        parser = ProwlerParser()
        findings = parser.parse(payload)

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        issues_created = 0
        control_tests = 0

        try:
            for finding in findings:
                sev = finding["severity"]
                if finding["result"] == "fail":
                    counts[sev] = counts.get(sev, 0) + 1

                finding["resolved_framework_refs"] = base.resolve_framework_refs(finding.get("framework_refs", []))
                base.create_control_test_result(
                    org_id=org_id,
                    check_key=f"prowler_{finding['check_id']}",
                    check_type=finding["control_type"],
                    result=finding["result"],
                    severity=sev,
                    detail=finding,
                    source="prowler",
                )
                control_tests += 1

                if finding["result"] == "fail" and sev in ("critical", "high"):
                    base.create_issue(
                        org_id=org_id,
                        title=f"Cloud Security Finding: {finding['check_title']}",
                        description=(
                            f"{finding['description']}\n\n"
                            f"Resource: {finding['resource_id']}\n"
                            f"Region: {finding['region']}\n"
                            f"Remediation: {finding['remediation']}"
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
            action="security.prowler_scan_ingested",
            entity_type="security_scan_jobs",
            organization_id=org_id,
            entity_id=job.id,
            metadata_json={
                "total_findings": len(findings),
                "issues_created": issues_created,
            },
        )

        return {
            "scan_job_id": str(job.id),
            "scan_source": "prowler",
            "total_findings": len(findings),
            "failed_count": sum(counts.values()),
            "critical_count": counts.get("critical", 0),
            "high_count": counts.get("high", 0),
            "issues_created": issues_created,
            "control_tests_created": control_tests,
        }
