from uuid import UUID

from pydantic import BaseModel


class PermissionRead(BaseModel):
    id: UUID
    key: str
    description: str | None = None
