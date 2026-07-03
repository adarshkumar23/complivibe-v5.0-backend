from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.security.parsers.openscap_parser import OpenSCAPParser
from app.integrations.security.services.base_service import SecurityIngestBaseService
from app.models.openscap_rule_mapping import OpenSCAPRuleMapping
from app.models.security_scan_job import SecurityScanJob
from app.services.audit_service import AuditService


class OpenSCAPIngestService:
    def process(self, org_id: uuid.UUID, xml_content: str, db: Session) -> dict:
        if not isinstance(xml_content, str) or not xml_content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed OpenSCAP payload")

        base = SecurityIngestBaseService(db)
        mappings = db.execute(select(OpenSCAPRuleMapping)).scalars().all()

        job = SecurityScanJob(
            organization_id=org_id,
            scan_source="openscap",
            scan_type="compliance",
            status="processing",
            source_metadata={},
        )
        db.add(job)
        db.flush()

        parser = OpenSCAPParser()
        try:
            findings = parser.parse(xml_content)
        except ValueError as exc:
            job.status = "failed"
            job.error_message = str(exc)[:1000]
            job.completed_at = datetime.now(UTC)
            db.flush()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        issues_created = 0
        control_tests = 0
        failed_count = 0

        try:
            for finding in findings:
                if finding["result"] == "fail":
                    sev = finding["severity"]
                    counts[sev] = counts.get(sev, 0) + 1
                    failed_count += 1

                control_family, control_type = parser.map_rule_to_control_family(finding["rule_id"], mappings)
                finding["control_family"] = control_family

                base.create_control_test_result(
                    org_id=org_id,
                    check_key=f"openscap_{finding['rule_id']}",
                    check_type=control_type,
                    result=finding["result"],
                    severity=finding["severity"],
                    detail=finding,
                    source="openscap",
                )
                control_tests += 1

                if finding["result"] == "fail" and finding["severity"] in ("critical", "high"):
                    base.create_issue(
                        org_id=org_id,
                        title=f"OpenSCAP Finding: {finding['rule_id'][-50:]}",
                        description=(
                            "SCAP rule failed.\n"
                            f"Rule: {finding['rule_id']}\n"
                            f"Severity: {finding['severity']}\n"
                            f"CCE: {finding.get('cce_id') or 'N/A'}\n"
                            f"Control family: {control_family} (NIST 800-53)"
                        ),
                        severity=finding["severity"],
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
            action="security.openscap_scan_ingested",
            entity_type="security_scan_jobs",
            organization_id=org_id,
            entity_id=job.id,
            metadata_json={
                "total_findings": len(findings),
                "failed_count": failed_count,
                "issues_created": issues_created,
            },
        )

        return {
            "scan_job_id": str(job.id),
            "scan_source": "openscap",
            "total_findings": len(findings),
            "failed_count": failed_count,
            "critical_count": counts.get("critical", 0),
            "high_count": counts.get("high", 0),
            "issues_created": issues_created,
            "control_tests_created": control_tests,
        }
