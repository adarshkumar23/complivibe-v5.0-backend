from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_organization, get_db, require_permission
from app.core.rate_limiter import rate_limiter
from app.integrations.security.schemas import (
    OpenSCAPIngestResponse,
    ProwlerIngestResponse,
    ScanJobResponse,
    TrivyIngestResponse,
    WazuhIngestResponse,
)
from app.integrations.security.services.base_service import SecurityIngestBaseService
from app.integrations.security.services.openscap_ingest_service import OpenSCAPIngestService
from app.integrations.security.services.prowler_ingest_service import ProwlerIngestService
from app.integrations.security.services.scan_job_service import ScanJobService
from app.integrations.security.services.trivy_ingest_service import TrivyIngestService
from app.integrations.security.services.wazuh_ingest_service import WazuhIngestService
from app.models.membership import Membership
from app.models.organization import Organization

router = APIRouter(prefix="/security", tags=["security-integrations"])


@router.post("/ingest/trivy", response_model=TrivyIngestResponse)
@rate_limiter.limiter.limit("30/minute")
def ingest_trivy_results(
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> TrivyIngestResponse:
    org_id = SecurityIngestBaseService(db).resolve_org_by_api_key(x_complivibe_key or "")
    summary = TrivyIngestService().process(org_id=org_id, payload=payload, db=db)
    db.commit()
    return TrivyIngestResponse(**summary)


@router.post("/ingest/prowler", response_model=ProwlerIngestResponse)
@rate_limiter.limiter.limit("30/minute")
def ingest_prowler_results(
    request: Request,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> ProwlerIngestResponse:
    org_id = SecurityIngestBaseService(db).resolve_org_by_api_key(x_complivibe_key or "")
    summary = ProwlerIngestService().process(org_id=org_id, payload=payload, db=db)
    db.commit()
    return ProwlerIngestResponse(**summary)


@router.post("/ingest/openscap", response_model=OpenSCAPIngestResponse)
@rate_limiter.limiter.limit("30/minute")
async def ingest_openscap_results(
    request: Request,
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> OpenSCAPIngestResponse:
    org_id = SecurityIngestBaseService(db).resolve_org_by_api_key(x_complivibe_key or "")
    xml_payload = (await request.body()).decode("utf-8", errors="ignore")
    summary = OpenSCAPIngestService().process(org_id=org_id, xml_content=xml_payload, db=db)
    db.commit()
    return OpenSCAPIngestResponse(**summary)


@router.post("/ingest/wazuh", response_model=WazuhIngestResponse)
@rate_limiter.limiter.limit("30/minute")
def ingest_wazuh_results(
    request: Request,
    payload: Any = Body(...),
    db: Session = Depends(get_db),
    x_complivibe_key: str | None = Header(default=None, alias="X-CompliVibe-Key"),
) -> WazuhIngestResponse:
    org_id = SecurityIngestBaseService(db).resolve_org_by_api_key(x_complivibe_key or "")
    summary = WazuhIngestService().process(org_id=org_id, payload=payload, db=db)
    db.commit()
    return WazuhIngestResponse(**summary)


@router.get("/scan-jobs", response_model=list[ScanJobResponse])
def list_scan_jobs(
    scan_source: str | None = Query(default=None),
    status_value: str | None = Query(default=None, alias="status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> list[ScanJobResponse]:
    rows = ScanJobService().list_jobs(
        org_id=organization.id,
        scan_source=scan_source,
        status_value=status_value,
        skip=skip,
        limit=limit,
        db=db,
    )
    return [ScanJobResponse.model_validate(row) for row in rows]


@router.get("/scan-jobs/summary")
def get_scan_jobs_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> dict:
    return ScanJobService().get_summary(org_id=organization.id, db=db)


@router.get("/scan-jobs/{job_id}", response_model=ScanJobResponse)
def get_scan_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("compliance:read")),
) -> ScanJobResponse:
    row = ScanJobService().get_job(org_id=organization.id, job_id=job_id, db=db)
    return ScanJobResponse.model_validate(row)
