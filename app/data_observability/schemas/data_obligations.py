import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DataAssetObligationLinkCreate(BaseModel):
    obligation_id: uuid.UUID
    link_type: str
    justification: str | None = None


class DataAssetObligationLinkRead(BaseModel):
    data_asset_id: str
    obligation_id: str
    obligation_ref: str
    obligation_title: str
    framework_code: str
    framework_name: str
    link_type: str
    justification: str | None
    linked_at: datetime


class DataObligationCoverageRead(BaseModel):
    total_assets: int
    linked_assets: int
    unlinked_assets: int
    coverage_pct: float
    by_link_type: dict[str, int]
    by_framework: dict[str, dict]


class DataObligationSuggestionRead(BaseModel):
    obligation_id: str
    obligation_ref: str
    obligation_title: str
    framework_code: str
    framework_name: str
    reason: str


class ObligationAssetRead(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    classification_type: str | None
    sensitivity_tier: str | None
    link_type: str
    justification: str | None
