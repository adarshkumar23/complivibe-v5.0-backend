from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.import_job import (
    ImportCommitRead,
    ImportDryRunPreviewRead,
    ImportJobCreateRequest,
    ImportJobRead,
    ImportProgressRead,
)
from app.services.import_job_service import ImportJobService

router = APIRouter(prefix="/import", tags=["import-jobs"])


def _job_read(row: Any) -> ImportJobRead:
    return ImportJobRead(
        id=row.id,
        organization_id=row.organization_id,
        source_tool=row.source_tool,
        status=row.status,
        progress_current=row.progress_current,
        progress_total=row.progress_total,
        dry_run=row.dry_run,
        conflict_strategy=row.conflict_strategy,
        error_summary=row.error_summary,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/{source}", response_model=ImportJobRead, status_code=status.HTTP_201_CREATED)
def create_import_job(
    source: str,
    payload: ImportJobCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("imports:create")),
) -> ImportJobRead:
    if source not in {"vanta", "drata", "sprinto", "scrut", "generic"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported import source")

    raw_payload: dict[str, Any] = {}
    if payload.csv_content:
        raw_payload["csv_content"] = payload.csv_content
    if payload.records:
        raw_payload["records"] = payload.records
    if payload.source_payload:
        raw_payload.update(payload.source_payload)

    job = ImportJobService(db).create_job(
        organization_id=organization.id,
        source_tool=source,
        payload=raw_payload,
        dry_run=payload.dry_run,
        conflict_strategy=payload.conflict_strategy,
        created_by=current_user.id,
    )
    db.commit()
    db.refresh(job)

    ImportJobService(db).enqueue_preview_job(request.app, job.id)
    db.commit()
    db.refresh(job)
    return _job_read(job)


@router.get("/{job_id}/progress", response_model=ImportProgressRead)
def get_import_job_progress(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("imports:read")),
) -> ImportProgressRead:
    service = ImportJobService(db)
    job = service.require_job(organization.id, job_id)
    return ImportProgressRead(job=_job_read(job), result_json=job.result_json)


@router.post("/{job_id}/dry-run-preview", response_model=ImportDryRunPreviewRead)
def dry_run_preview(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("imports:preview")),
) -> ImportDryRunPreviewRead:
    payload = ImportJobService(db).preview(organization.id, job_id)
    db.commit()
    return ImportDryRunPreviewRead(**payload)


@router.post("/{job_id}/commit", response_model=ImportCommitRead)
def commit_import_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("imports:commit")),
) -> ImportCommitRead:
    payload = ImportJobService(db).commit(organization.id, job_id, current_user.id)
    db.commit()
    return ImportCommitRead(**payload)
