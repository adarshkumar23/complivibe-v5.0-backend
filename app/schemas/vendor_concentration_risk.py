from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class VendorConcentrationRiskVendorShare(BaseModel):
    vendor_id: UUID
    vendor_name: str
    exposure_count: int
    share_basis_points: int


class VendorConcentrationRiskDetectionRead(BaseModel):
    id: UUID | None = None
    organization_id: UUID
    status: str
    hhi_score: int
    threshold_hhi_score: int
    top_vendor_id: UUID | None = None
    top_vendor_name: str | None = None
    top_vendor_share_basis_points: int
    exposure_count: int
    critical_vendor_count: int
    dependency_count: int
    risk_id: UUID | None = None
    convention_source_title: str
    convention_source_url: str
    criticality_source_title: str
    criticality_source_url: str
    evidence_json: dict | None = None
    recomputed_by_user_id: UUID | None = None
    recomputed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VendorConcentrationRiskRecomputeRequest(BaseModel):
    threshold_hhi_score: int = Field(default=1800, ge=1, le=10000)


class VendorConcentrationRiskRecomputeResponse(BaseModel):
    detection: VendorConcentrationRiskDetectionRead
    risk_created: bool
    state_changed: bool
