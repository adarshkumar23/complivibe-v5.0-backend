from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.integrations.security.parsers.trivy_parser import TrivyParser
from app.integrations.security.services.base_service import SecurityIngestBaseService
from app.models.security_scan_job import SecurityScanJob
from app.services.audit_service import AuditService


class TrivyIngestService:
    def process(
        self,
        org_id: uuid.UUID,
        payload: dict,
        db: Session,
    ) -> dict:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Trivy payload")

        base = SecurityIngestBaseService(db)
        job = SecurityScanJob(
            organization_id=org_id,
            scan_source="trivy",
            scan_type="container_image",
            status="processing",
            source_metadata={
                "artifact": payload.get("ArtifactName", "unknown"),
                "schema_version": payload.get("SchemaVersion"),
            },
        )
        db.add(job)
        db.flush()

        parser = TrivyParser()
        findings = parser.parse(payload)

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        issues_created = 0
        control_tests = 0

        try:
            for finding in findings:
                sev = finding["severity"]
                counts[sev] = counts.get(sev, 0) + 1

                base.create_control_test_result(
                    org_id=org_id,
                    check_key=f"trivy_{finding['cve_id']}",
                    check_type="vulnerability_scan",
                    result="fail",
                    severity=sev,
                    detail=finding,
                    source="trivy",
                )
                control_tests += 1

                if sev == "critical":
                    base.create_issue(
                        org_id=org_id,
                        title=f"Critical CVE: {finding['cve_id']} in {finding['package']}",
                        description=(
                            f"{finding['title']}\n\n"
                            f"Package: {finding['package']} {finding['installed_version']}\n"
                            f"Fix: {finding.get('fixed_version') or 'N/A'}\n"
                            f"Target: {finding['target']}"
                        ),
                        severity="critical",
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
            action="security.trivy_scan_ingested",
            entity_type="security_scan_jobs",
            organization_id=org_id,
            entity_id=job.id,
            metadata_json={
                "total_findings": len(findings),
                "critical": counts.get("critical", 0),
                "issues_created": issues_created,
            },
        )

        return {
            "scan_job_id": str(job.id),
            "scan_source": "trivy",
            "total_findings": len(findings),
            "critical_count": counts.get("critical", 0),
            "high_count": counts.get("high", 0),
            "medium_count": counts.get("medium", 0),
            "low_count": counts.get("low", 0),
            "issues_created": issues_created,
            "control_tests_created": control_tests,
        }
