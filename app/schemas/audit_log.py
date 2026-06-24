from uuid import UUID

from app.schemas.common import UUIDTimestampSchema


class AuditLogRead(UUIDTimestampSchema):
    organization_id: UUID
    actor_user_id: UUID | None = None
    action: str
    entity_type: str
    entity_id: UUID | None = None
    before_json: dict
    after_json: dict
    metadata_json: dict
    ip_address: str | None = None
    user_agent: str | None = None
