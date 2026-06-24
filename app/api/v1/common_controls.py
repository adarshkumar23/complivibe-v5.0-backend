import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.compliance.services.common_controls_service import CommonControlsService
from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.common_control_evidence_coverage import CommonControlEvidenceCoverage
from app.models.common_control_mapping import CommonControlMapping
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common_controls import (
    CommonControlCoverageReport,
    CommonControlEvidenceCoverageCreate,
    CommonControlEvidenceCoverageRead,
    CommonControlMappingCreate,
    CommonControlMappingRead,
    CommonControlMappingUpdate,
    CommonControlsSummary,
    EvidenceReuseReport,
)

router = APIRouter(prefix="/compliance/common-controls", tags=["common-controls"])


def _mapping_read(row: CommonControlMapping) -> CommonControlMappingRead:
    return CommonControlMappingRead(
        id=row.id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        framework_id=row.framework_id,
        obligation_id=row.obligation_id,
        section_reference=row.section_reference,
        mapping_rationale=row.mapping_rationale,
        mapping_strength=row.mapping_strength,
        verified_by_user_id=row.verified_by_user_id,
        verified_at=row.verified_at,
        status=row.status,
        created_by_user_id=row.created_by_user_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _coverage_read(row: CommonControlEvidenceCoverage) -> CommonControlEvidenceCoverageRead:
    return CommonControlEvidenceCoverageRead(
        id=row.id,
        organization_id=row.organization_id,
        control_id=row.control_id,
        evidence_id=row.evidence_id,
        mapping_id=row.mapping_id,
        coverage_status=row.coverage_status,
        coverage_notes=row.coverage_notes,
        assessed_by_user_id=row.assessed_by_user_id,
        assessed_at=row.assessed_at,
        created_at=row.created_at,
    )


@router.post("/mappings", response_model=CommonControlMappingRead, status_code=status.HTTP_201_CREATED)
def create_common_control_mapping(
    payload: CommonControlMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> CommonControlMappingRead:
    service = CommonControlsService(db)
    row = service.create_mapping(
        control_id=payload.control_id,
        framework_id=payload.framework_id,
        obligation_id=payload.obligation_id,
        data=payload,
        org_id=organization.id,
        created_by_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _mapping_read(row)


@router.get("/summary", response_model=CommonControlsSummary)
def get_common_controls_summary(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> CommonControlsSummary:
    return CommonControlsSummary(**CommonControlsService(db).get_common_controls_summary(organization.id))


@router.get("/mappings", response_model=list[CommonControlMappingRead])
def list_common_control_mappings(
    control_id: uuid.UUID | None = Query(default=None),
    framework_id: uuid.UUID | None = Query(default=None),
    mapping_strength: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> list[CommonControlMappingRead]:
    rows = CommonControlsService(db).list_mappings(
        organization.id,
        control_id=control_id,
        framework_id=framework_id,
        mapping_strength=mapping_strength,
        status_value=status_filter,
    )
    return [_mapping_read(row) for row in rows]


@router.patch("/mappings/{mapping_id}", response_model=CommonControlMappingRead)
def update_common_control_mapping(
    mapping_id: uuid.UUID,
    payload: CommonControlMappingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> CommonControlMappingRead:
    row = CommonControlsService(db).update_mapping(
        mapping_id=mapping_id,
        data=payload,
        org_id=organization.id,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _mapping_read(row)


@router.delete("/mappings/{mapping_id}", response_model=CommonControlMappingRead)
def deactivate_common_control_mapping(
    mapping_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> CommonControlMappingRead:
    row = CommonControlsService(db).deactivate_mapping(mapping_id, organization.id, current_user.id)
    db.commit()
    db.refresh(row)
    return _mapping_read(row)


@router.post("/evidence-coverage", response_model=CommonControlEvidenceCoverageRead, status_code=status.HTTP_201_CREATED)
def add_common_control_evidence_coverage(
    payload: CommonControlEvidenceCoverageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:write")),
) -> CommonControlEvidenceCoverageRead:
    row = CommonControlsService(db).add_evidence_coverage(
        org_id=organization.id,
        control_id=payload.control_id,
        evidence_id=payload.evidence_id,
        mapping_id=payload.mapping_id,
        coverage_status=payload.coverage_status,
        coverage_notes=payload.coverage_notes,
        actor_user_id=current_user.id,
    )
    db.commit()
    db.refresh(row)
    return _coverage_read(row)


@router.get("/coverage/{control_id}", response_model=CommonControlCoverageReport)
def get_common_control_coverage(
    control_id: uuid.UUID,
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> CommonControlCoverageReport:
    return CommonControlCoverageReport(**CommonControlsService(db).get_coverage_report(control_id, organization.id))


@router.get("/evidence-reuse", response_model=EvidenceReuseReport)
def get_evidence_reuse_report(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("controls:read")),
) -> EvidenceReuseReport:
    return EvidenceReuseReport(**CommonControlsService(db).get_evidence_reuse_report(organization.id))
