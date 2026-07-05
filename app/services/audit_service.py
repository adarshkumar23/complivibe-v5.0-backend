import logging
import uuid

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


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
        self._dispatch_search_indexing(action=action, entity_type=entity_type, entity_id=entity_id, organization_id=organization_id)
        return log

    def _dispatch_search_indexing(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID | None,
        organization_id: uuid.UUID,
    ) -> None:
        # Lightweight allowlist dispatch: only a handful of entity types feed
        # the cross-entity search index, so unrelated audit-logged actions
        # (there are dozens of entity types) never pay any Meilisearch cost.
        # Imported lazily to avoid a hard import-time dependency from every
        # caller of AuditService on the meilisearch client package.
        from app.services.search_indexing_service import TRACKED_ENTITY_TYPES

        if entity_type not in TRACKED_ENTITY_TYPES:
            return
        try:
            from app.services.search_indexing_service import SearchIndexingService

            SearchIndexingService(self.db).handle_audit_event(
                entity_type=entity_type,
                entity_id=entity_id,
                organization_id=organization_id,
                action=action,
            )
        except Exception:  # noqa: BLE001 - search indexing must never break an audited write
            logger.warning(
                "search indexing dispatch failed for entity_type=%s entity_id=%s",
                entity_type,
                entity_id,
                exc_info=True,
            )
