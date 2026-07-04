import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.compliance.services.oscal_export_service import OSCALExportService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.oscal_export_job import OscalExportJob
from app.models.user import User
from app.schemas.oscal_export import (
    OSCALExportCreate,
    OSCALExportJobDetail,
    OSCALExportJobRead,
    OSCALExportSummary,
    OSCALValidateResponse,
)

router = APIRouter(prefix="/compliance/oscal", tags=["oscal"])


def _read_job(row: OscalExportJob) -> OSCALExportJobRead:
    return OSCALExportJobRead(
        id=row.id,
        organization_id=row.organization_id,
        export_type=row.export_type,
        framework_id=row.framework_id,
        status=row.status,
        oscal_version=row.oscal_version,
        result_size_bytes=row.result_size_bytes,
        error_message=row.error_message,
        requested_by_user_id=row.requested_by_user_id,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_at=row.created_at,
    )


@router.post("/export", response_model=OSCALExportJobDetail)
def create_and_build_export(
    payload: OSCALExportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> OSCALExportJobDetail:
    service = OSCALExportService(db)
    if payload.framework_id is not None:
        _ = service.validate_export_framework(organization.id, payload.framework_id)
    job = service.create_job(
        export_type=payload.export_type,
        framework_id=payload.framework_id,
        org_id=organization.id,
        requested_by_user_id=current_user.id,
    )
    job = service.build(job.id, organization.id)
    db.commit()
    db.refresh(job)

    result_json = job.result_json if job.status == "complete" else None
    return OSCALExportJobDetail(**_read_job(job).model_dump(), result_json=result_json)


@router.get("/summary", response_model=OSCALExportSummary)
def oscal_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> OSCALExportSummary:
    return OSCALExportSummary(**OSCALExportService(db).summary(organization.id))


@router.get("/exports", response_model=list[OSCALExportJobRead])
def list_exports(
    status_filter: str | None = Query(default=None, alias="status"),
    export_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> list[OSCALExportJobRead]:
    rows = OSCALExportService(db).list_jobs(
        organization.id,
        status_filter=status_filter,
        export_type=export_type,
    )
    return [_read_job(row) for row in rows]


@router.get("/exports/{job_id}", response_model=OSCALExportJobDetail)
def get_export_detail(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> OSCALExportJobDetail:
    row = OSCALExportService(db).require_job_in_org(job_id, organization.id)
    result_json = row.result_json if row.status == "complete" else None
    return OSCALExportJobDetail(**_read_job(row).model_dump(), result_json=result_json)


@router.get("/exports/{job_id}/download")
def download_export(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> Response:
    row = OSCALExportService(db).require_job_in_org(job_id, organization.id)
    if row.status != "complete" or row.result_json is None:
        raise HTTPException(
            status_code=422,
            detail=f"Export job not yet complete. Current status: {row.status}",
        )

    payload = json.dumps(row.result_json).encode("utf-8")
    today = datetime.now(UTC).date().isoformat()
    filename = f"complivibe-oscal-{row.export_type}-{today}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=payload, media_type="application/json", headers=headers)


@router.get("/exports/{job_id}/validate", response_model=OSCALValidateResponse)
def validate_export(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("reports:read")),
) -> OSCALValidateResponse:
    service = OSCALExportService(db)
    row = service.require_job_in_org(job_id, organization.id)
    if row.status != "complete" or row.result_json is None:
        raise HTTPException(
            status_code=422,
            detail=f"Export job not yet complete. Current status: {row.status}",
        )

    errors = service.validate_oscal_structure(row.result_json, row.export_type)
    return OSCALValidateResponse(
        valid=len(errors) == 0,
        errors=errors,
        oscal_version=row.oscal_version,
        export_type=row.export_type,
        validated_at=service.utcnow(),
    )
