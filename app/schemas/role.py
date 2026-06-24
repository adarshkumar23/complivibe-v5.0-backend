from uuid import UUID

from pydantic import BaseModel


class RoleRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    is_system: bool
    permissions: list[str]
