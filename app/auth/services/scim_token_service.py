from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.scim_token import ScimToken
from app.services.audit_service import AuditService


class ScimTokenService:
    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def generate_token(
        self,
        org_id: uuid.UUID,
        description: str,
        created_by: uuid.UUID,
        expires_at: datetime | None,
        db: Session,
    ) -> dict:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        record = ScimToken(
            organization_id=org_id,
            token_hash=token_hash,
            description=description,
            is_active=True,
            created_by=created_by,
            expires_at=expires_at,
        )
        db.add(record)
        db.flush()

        AuditService(db).write_audit_log(
            action="scim_token.created",
            entity_type="scim_tokens",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=record.id,
        )

        return {
            "token_id": str(record.id),
            "raw_token": raw_token,
            "description": description,
            "warning": "Store this token securely. It will not be shown again.",
        }

    def list_tokens(self, org_id: uuid.UUID, db: Session) -> list[ScimToken]:
        return db.execute(
            select(ScimToken).where(
                ScimToken.organization_id == org_id,
                ScimToken.deleted_at.is_(None),
            )
        ).scalars().all()

    def revoke_token(self, org_id: uuid.UUID, token_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> ScimToken:
        row = self._require_token(org_id, token_id, db)
        row.is_active = False
        db.flush()
        AuditService(db).write_audit_log(
            action="scim_token.revoked",
            entity_type="scim_tokens",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=row.id,
        )
        return row

    def delete_token(self, org_id: uuid.UUID, token_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
        row = self._require_token(org_id, token_id, db)
        row.deleted_at = self.utcnow()
        row.is_active = False
        db.flush()
        AuditService(db).write_audit_log(
            action="scim_token.deleted",
            entity_type="scim_tokens",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=row.id,
        )

    @staticmethod
    def _require_token(org_id: uuid.UUID, token_id: uuid.UUID, db: Session) -> ScimToken:
        row = db.execute(
            select(ScimToken).where(
                ScimToken.organization_id == org_id,
                ScimToken.id == token_id,
                ScimToken.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SCIM token not found")
        return row
