import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.ot_ics_agent import OtIcsAgent
from app.models.ot_ics_asset import OtIcsAsset
from app.models.ot_ics_finding import OtIcsFinding
from app.models.user import User
from app.schemas.ot_ics import (
    OtIcsAgentCreate,
    OtIcsAgentRegistrationResponse,
    OtIcsAgentResponse,
    OtIcsAssetCreate,
    OtIcsAssetResponse,
    OtIcsAssetUpdate,
    OtIcsFindingIngestRequest,
    OtIcsFindingIngestResponse,
    OtIcsFindingResolveRequest,
    OtIcsFindingResponse,
    OtIcsFindingSummaryResponse,
)
from app.services.ot_ics_service import (
    OtIcsAgentService,
    OtIcsAssetService,
    OtIcsFindingService,
    get_ot_ics_agent_from_token,
)

router = APIRouter(prefix="/ot-ics", tags=["ot-ics"])
ingest_router = APIRouter(prefix="/ot-ics", tags=["ot-ics"])


def _agent_read(row: OtIcsAgent) -> OtIcsAgentResponse:
    return OtIcsAgentResponse(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        last_seen_at=row.last_seen_at,
        created_at=row.created_at,
    )


def _asset_read(row: OtIcsAsset) -> OtIcsAssetResponse:
    return OtIcsAssetResponse(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        asset_type=row.asset_type,
        network_segment=row.network_segment,
        criticality=row.criticality,
        linked_data_asset_id=row.linked_data_asset_id,
        status=row.status,
        description=row.description,
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _finding_read(row: OtIcsFinding) -> OtIcsFindingResponse:
    return OtIcsFindingResponse(
        id=row.id,
        organization_id=row.organization_id,
        asset_id=row.asset_id,
        agent_id=row.agent_id,
        finding_type=row.finding_type,
        severity=row.severity,
        description=row.description,
        raw_payload=row.raw_payload,
        detected_at=row.detected_at,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
    )


# --- Agents ---


@router.post("/agents", response_model=OtIcsAgentRegistrationResponse, status_code=status.HTTP_201_CREATED)
def register_ot_ics_agent(
    payload: OtIcsAgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> OtIcsAgentRegistrationResponse:
    service = OtIcsAgentService(db)
    row, token = service.register_agent(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return OtIcsAgentRegistrationResponse(**_agent_read(row).model_dump(), token=token)


@router.get("/agents", response_model=list[OtIcsAgentResponse])
def list_ot_ics_agents(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> list[OtIcsAgentResponse]:
    rows = OtIcsAgentService(db).list_agents(organization.id)
    return [_agent_read(row) for row in rows]


@router.delete("/agents/{agent_id}", response_model=OtIcsAgentResponse)
def deregister_ot_ics_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> OtIcsAgentResponse:
    row = OtIcsAgentService(db).deregister_agent(organization.id, agent_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _agent_read(row)


# --- Assets ---


@router.post("/assets", response_model=OtIcsAssetResponse, status_code=status.HTTP_201_CREATED)
def create_ot_ics_asset(
    payload: OtIcsAssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> OtIcsAssetResponse:
    row = OtIcsAssetService(db).create_asset(organization.id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _asset_read(row)


@router.get("/assets", response_model=list[OtIcsAssetResponse])
def list_ot_ics_assets(
    asset_type: str | None = Query(default=None),
    criticality: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    network_segment: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:read")),
) -> list[OtIcsAssetResponse]:
    rows = OtIcsAssetService(db).list_assets(
        organization.id,
        asset_type=asset_type,
        criticality=criticality,
        status_filter=status_filter,
        network_segment=network_segment,
    )
    return [_asset_read(row) for row in rows]


@router.get("/assets/{asset_id}", response_model=OtIcsAssetResponse)
def get_ot_ics_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:read")),
) -> OtIcsAssetResponse:
    row = OtIcsAssetService(db).get_asset(organization.id, asset_id)
    return _asset_read(row)


@router.patch("/assets/{asset_id}", response_model=OtIcsAssetResponse)
def update_ot_ics_asset(
    asset_id: uuid.UUID,
    payload: OtIcsAssetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> OtIcsAssetResponse:
    row = OtIcsAssetService(db).update_asset(organization.id, asset_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _asset_read(row)


@router.delete("/assets/{asset_id}", response_model=OtIcsAssetResponse)
def delete_ot_ics_asset(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> OtIcsAssetResponse:
    row = OtIcsAssetService(db).delete_asset(organization.id, asset_id, current_user.id)
    db.commit()
    db.refresh(row)
    return _asset_read(row)


# --- Findings ---


@ingest_router.post("/findings/ingest", response_model=OtIcsFindingIngestResponse)
def ingest_ot_ics_finding(
    payload: OtIcsFindingIngestRequest,
    agent: OtIcsAgent = Depends(get_ot_ics_agent_from_token),
    db: Session = Depends(get_db),
) -> OtIcsFindingIngestResponse:
    row = OtIcsFindingService(db).ingest_finding(agent, payload)
    db.commit()
    db.refresh(row)
    return OtIcsFindingIngestResponse(
        finding_id=row.id,
        asset_id=row.asset_id,
        severity=row.severity,
        finding_type=row.finding_type,
        detected_at=row.detected_at,
    )


@router.get("/findings", response_model=list[OtIcsFindingResponse])
def list_ot_ics_findings(
    asset_id: uuid.UUID | None = Query(default=None),
    severity: str | None = Query(default=None),
    finding_type: str | None = Query(default=None),
    unresolved_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:read")),
) -> list[OtIcsFindingResponse]:
    rows = OtIcsFindingService(db).list_findings(
        organization.id,
        asset_id=asset_id,
        severity=severity,
        finding_type=finding_type,
        unresolved_only=unresolved_only,
    )
    return [_finding_read(row) for row in rows]


@router.post("/findings/{finding_id}/resolve", response_model=OtIcsFindingResponse)
def resolve_ot_ics_finding(
    finding_id: uuid.UUID,
    payload: OtIcsFindingResolveRequest = OtIcsFindingResolveRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:manage")),
) -> OtIcsFindingResponse:
    row = OtIcsFindingService(db).resolve_finding(organization.id, finding_id, payload, current_user.id)
    db.commit()
    db.refresh(row)
    return _finding_read(row)


@router.get("/findings/summary", response_model=OtIcsFindingSummaryResponse)
def ot_ics_findings_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("ot_ics_assets:read")),
) -> OtIcsFindingSummaryResponse:
    payload = OtIcsFindingService(db).get_summary(organization.id)
    return OtIcsFindingSummaryResponse(**payload)
