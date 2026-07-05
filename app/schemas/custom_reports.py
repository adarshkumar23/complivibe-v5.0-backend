from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

ALLOWED_CUSTOM_REPORT_TEMPLATE_TYPES = {
    "custom",
    "csrd_esrs",
    "gri",
    "tcfd",
    "issb",
}

ALLOWED_CUSTOM_REPORT_SECTIONS = {
    "executive_summary",
    "framework_readiness",
    "control_health",
    "risk_summary",
    "vendor_risk",
    "evidence_status",
    "open_issues",
    "policy_status",
    "ai_governance_summary",
    "esg_disclosure_template",
}


class CustomReportTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    template_type: str = Field(default="custom", pattern="^(custom|csrd_esrs|gri|tcfd|issb)$")
    sections: list[str]
    disclosure_structure: list[dict] | None = None
    framework_filter: list[UUID] | None = None
    date_range_days: int = Field(default=90, ge=7, le=365)


class CustomReportTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    template_type: str | None = Field(default=None, pattern="^(custom|csrd_esrs|gri|tcfd|issb)$")
    sections: list[str] | None = None
    disclosure_structure: list[dict] | None = None
    framework_filter: list[UUID] | None = None
    date_range_days: int | None = Field(default=None, ge=7, le=365)


class CustomReportTemplateRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    template_type: str = "custom"
    system_template_key: str | None = None
    sections: list[str]
    disclosure_structure: list[dict] | dict | None = None
    framework_filter: list[str] | list[UUID] | None = None
    date_range_days: int
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class CustomReportGenerateResponse(BaseModel):
    report_id: UUID
    report_type: str
    title: str
