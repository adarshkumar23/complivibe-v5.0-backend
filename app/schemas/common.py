from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AppBaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UUIDTimestampSchema(AppBaseSchema):
    id: UUID
    created_at: datetime
    updated_at: datetime
