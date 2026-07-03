from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.security_scan_job import SecurityScanJob


class ScanJobService:
    def list_jobs(
        self,
        org_id: uuid.UUID,
        scan_source: str | None = None,
        status_value: str | None = None,
        skip: int = 0,
        limit: int = 50,
        db: Session | None = None,
    ) -> list[SecurityScanJob]:
        if db is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database session is required")

        query = db.query(SecurityScanJob).filter(SecurityScanJob.organization_id == org_id)
        if scan_source:
            query = query.filter(SecurityScanJob.scan_source == scan_source)
        if status_value:
            query = query.filter(SecurityScanJob.status == status_value)

        return query.order_by(SecurityScanJob.submitted_at.desc()).offset(skip).limit(limit).all()

    def get_job(
        self,
        org_id: uuid.UUID,
        job_id: uuid.UUID,
        db: Session,
    ) -> SecurityScanJob:
        job = db.query(SecurityScanJob).filter(
            SecurityScanJob.id == job_id,
            SecurityScanJob.organization_id == org_id,
        ).first()
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")
        return job

    def get_summary(self, org_id: uuid.UUID, db: Session) -> dict:
        jobs = db.query(SecurityScanJob).filter(
            SecurityScanJob.organization_id == org_id,
            SecurityScanJob.status == "completed",
        ).all()

        by_source: dict[str, int] = {}
        for row in jobs:
            by_source[row.scan_source] = by_source.get(row.scan_source, 0) + 1

        return {
            "total_scans": len(jobs),
            "by_source": by_source,
            "total_critical": sum(row.critical_count for row in jobs),
            "total_issues_created": sum(row.issues_created for row in jobs),
            "last_scan_at": max((row.completed_at for row in jobs if row.completed_at is not None), default=None),
        }
