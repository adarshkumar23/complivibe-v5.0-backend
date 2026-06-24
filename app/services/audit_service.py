import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def write_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        before_json: dict | None = None,
        after_json: dict | None = None,
        metadata_json: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before_json or {},
            after_json=after_json or {},
            metadata_json=metadata_json or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(log)
        self.db.flush()
        return log
