from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RemediationSuggestionRead(BaseModel):
    id: UUID
    organization_id: UUID
    issue_id: UUID
    suggestion_text: str
    suggestion_source: str
    source_key: str
    applied: bool
    dismissed: bool
    created_at: datetime
    updated_at: datetime
