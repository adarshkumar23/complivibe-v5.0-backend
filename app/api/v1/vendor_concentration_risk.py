from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.models.vendor_concentration_risk import VendorConcentrationRiskDetection
from app.schemas.vendor_concentration_risk import (
    VendorConcentrationRiskDetectionRead,
    VendorConcentrationRiskRecomputeRequest,
    VendorConcentrationRiskRecomputeResponse,
)
from app.services.audit_service import AuditService
from app.services.vendor_concentration_risk_service import (
    CONCENTRATION_SOURCE_TITLE,
    CONCENTRATION_SOURCE_URL,
    CRITICALITY_SOURCE_TITLE,
    CRITICALITY_SOURCE_URL,
    HHI_HIGHLY_CONCENTRATED_THRESHOLD,
    VendorConcentrationRiskService,
)

router = APIRouter(prefix="/vendor-concentration-risk", tags=["vendor-concentration-risk"])


def _detection_read(row: VendorConcentrationRiskDetection | None, organization_id: uuid.UUID) -> VendorConcentrationRiskDetectionRead:
    if row is None:
        return VendorConcentrationRiskDetectionRead(
            organization_id=organization_id,
            status="not_computed",
            hhi_score=0,
            threshold_hhi_score=HHI_HIGHLY_CONCENTRATED_THRESHOLD,
            top_vendor_share_basis_points=0,
            exposure_count=0,
            critical_vendor_count=0,
            dependency_count=0,
            convention_source_title=CONCENTRATION_SOURCE_TITLE,
            convention_source_url=CONCENTRATION_SOURCE_URL,
            criticality_source_title=CRITICALITY_SOURCE_TITLE,
            criticality_source_url=CRITICALITY_SOURCE_URL,
        )
    return VendorConcentrationRiskDetectionRead(
        id=row.id,
        organization_id=row.organization_id,
        status=row.status,
        hhi_score=row.hhi_score,
        threshold_hhi_score=row.threshold_hhi_score,
        top_vendor_id=row.top_vendor_id,
        top_vendor_name=row.top_vendor_name,
        top_vendor_share_basis_points=row.top_vendor_share_basis_points,
        exposure_count=row.exposure_count,
        critical_vendor_count=row.critical_vendor_count,
        dependency_count=row.dependency_count,
        risk_id=row.risk_id,
        convention_source_title=row.convention_source_title,
        convention_source_url=row.convention_source_url,
        criticality_source_title=row.criticality_source_title,
        criticality_source_url=row.criticality_source_url,
        evidence_json=row.evidence_json,
        recomputed_by_user_id=row.recomputed_by_user_id,
        recomputed_at=row.recomputed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=VendorConcentrationRiskDetectionRead)
def get_vendor_concentration_risk(
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_concentration_risk:read")),
) -> VendorConcentrationRiskDetectionRead:
    row = VendorConcentrationRiskService(db).current(organization.id)
    return _detection_read(row, organization.id)


@router.post("/recompute", response_model=VendorConcentrationRiskRecomputeResponse, status_code=status.HTTP_200_OK)
def recompute_vendor_concentration_risk(
    payload: VendorConcentrationRiskRecomputeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("vendor_concentration_risk:manage")),
) -> VendorConcentrationRiskRecomputeResponse:
    service = VendorConcentrationRiskService(db)
    before = service.current(organization.id)
    before_json = service._state_fingerprint(before)
    row, risk_created, state_changed = service.recompute(
        organization_id=organization.id,
        actor_user_id=current_user.id,
        threshold_hhi_score=payload.threshold_hhi_score,
    )
    if state_changed:
        AuditService(db).write_audit_log(
            action="vendor_concentration_risk.recomputed",
            entity_type="vendor_concentration_risk_detection",
            entity_id=row.id,
            organization_id=organization.id,
            actor_user_id=current_user.id,
            before_json=before_json,
            after_json=service._state_fingerprint(row),
            metadata_json={"source": "api", "risk_created": risk_created},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    db.commit()
    db.refresh(row)
    return VendorConcentrationRiskRecomputeResponse(
        detection=_detection_read(row, organization.id),
        risk_created=risk_created,
        state_changed=state_changed,
    )
