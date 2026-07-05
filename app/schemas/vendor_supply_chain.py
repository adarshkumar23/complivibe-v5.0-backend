from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class VendorSupplyChainLinkCreate(BaseModel):
    sub_vendor_id: UUID
    relationship_type: str = Field(default="supplier", min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=2000)


class VendorSupplyChainLinkRead(BaseModel):
    id: UUID
    parent_vendor_id: UUID
    sub_vendor_id: UUID
    relationship_type: str
    description: str | None = None
    is_active: bool


class VendorSupplyChainGraphRead(BaseModel):
    root_vendor_id: str
    depth: int
    nodes: list[dict]
    edges: list[dict]
    data_quality_findings: list[dict]
    open_alerts: list[dict]
