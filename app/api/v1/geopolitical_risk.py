import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_current_organization, get_db, require_permission
from app.models.membership import Membership
from app.models.organization import Organization
from app.models.user import User
from app.schemas.geopolitical_risk import (
    ExposedVendorRegion,
    ExposedVendorSummary,
    GeopoliticalIngestRequest,
    GeopoliticalIngestResponse,
    GeopoliticalRiskSignalResponse,
    GeopoliticalSummaryResponse,
    UnmonitoredVendorExposure,
    VendorGeopoliticalExposureCreate,
    VendorGeopoliticalExposureResponse,
)
from app.services.geopolitical_risk_service import GeopoliticalRiskService

router = APIRouter(prefix="/geopolitical-risk", tags=["geopolitical-risk"])


@router.post("/ingest", response_model=GeopoliticalIngestResponse, status_code=status.HTTP_200_OK)
def ingest_geopolitical_risk(
    payload: GeopoliticalIngestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("geopolitical_risk:manage")),
) -> GeopoliticalIngestResponse:
    result = GeopoliticalRiskService(db).ingest_from_gdelt(
        organization.id, payload.region_query, current_user.id, max_records=payload.max_records
    )
    return GeopoliticalIngestResponse(
        status=result["status"],
        source=result["source"],
        region_query=result["region_query"],
        signals_created=result["signals_created"],
        source_error=result["source_error"],
        signals=[GeopoliticalRiskSignalResponse.model_validate(row) for row in result["signals"]],
    )


@router.get("/signals", response_model=list[GeopoliticalRiskSignalResponse])
def list_geopolitical_signals(
    region: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("geopolitical_risk:read")),
) -> list[GeopoliticalRiskSignalResponse]:
    rows = GeopoliticalRiskService(db).list_signals(
        organization.id, region=region, category=category, severity=severity, skip=skip, limit=limit
    )
    return [GeopoliticalRiskSignalResponse.model_validate(row) for row in rows]


@router.get("/summary", response_model=GeopoliticalSummaryResponse)
def get_geopolitical_summary(
    business_unit_id: uuid.UUID | None = Query(default=None),
    vendor_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("geopolitical_risk:read")),
) -> GeopoliticalSummaryResponse:
    summary = GeopoliticalRiskService(db).get_summary(
        organization.id, business_unit_id=business_unit_id, vendor_id=vendor_id
    )
    return GeopoliticalSummaryResponse(
        organization_id=summary["organization_id"],
        regions_with_signals=summary["regions_with_signals"],
        exposed_vendors=[
            ExposedVendorSummary(
                vendor_id=item["vendor_id"],
                vendor_name=item["vendor_name"],
                business_unit_id=item["business_unit_id"],
                exposed_regions=[ExposedVendorRegion(**region) for region in item["exposed_regions"]],
                overall_max_severity=item["overall_max_severity"],
                total_signal_count=item["total_signal_count"],
            )
            for item in summary["exposed_vendors"]
        ],
        vendor_count_exposed=summary["vendor_count_exposed"],
        highest_severity_observed=summary["highest_severity_observed"],
        stale_regions=summary["stale_regions"],
        unmonitored_exposures=[
            UnmonitoredVendorExposure(**item) for item in summary["unmonitored_exposures"]
        ],
    )


@router.post("/vendor-exposures", response_model=VendorGeopoliticalExposureResponse, status_code=status.HTTP_201_CREATED)
def create_vendor_exposure(
    payload: VendorGeopoliticalExposureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("geopolitical_risk:manage")),
) -> VendorGeopoliticalExposureResponse:
    row = GeopoliticalRiskService(db).create_exposure(organization.id, payload, current_user.id)
    return VendorGeopoliticalExposureResponse.model_validate(row)


@router.get("/vendor-exposures", response_model=list[VendorGeopoliticalExposureResponse])
def list_vendor_exposures(
    vendor_id: uuid.UUID | None = Query(default=None),
    region: str | None = Query(default=None),
    db: Session = Depends(get_db),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("geopolitical_risk:read")),
) -> list[VendorGeopoliticalExposureResponse]:
    rows = GeopoliticalRiskService(db).list_exposures(organization.id, vendor_id=vendor_id, region=region)
    return [VendorGeopoliticalExposureResponse.model_validate(row) for row in rows]


@router.delete("/vendor-exposures/{exposure_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vendor_exposure(
    exposure_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    organization: Organization = Depends(get_current_organization),
    _: Membership = Depends(require_permission("geopolitical_risk:manage")),
) -> None:
    GeopoliticalRiskService(db).delete_exposure(organization.id, exposure_id, current_user.id)
