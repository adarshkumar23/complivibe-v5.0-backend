from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class OrgIssueSettingsRead(BaseModel):
    id: UUID
    organization_id: UUID
    require_rca_before_close: bool
    created_at: datetime
    updated_at: datetime


class OrgIssueSettingsUpdate(BaseModel):
    require_rca_before_close: bool
