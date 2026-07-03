import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas.sso import SSOConfigCreate, SSOConfigUpdate
from app.models.sso_config import SSOConfig
from app.services.audit_service import AuditService


class SSOConfigService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def create_config(
        self,
        org_id: uuid.UUID,
        data: SSOConfigCreate,
        created_by: uuid.UUID,
        db: Session,
    ) -> SSOConfig:
        existing = db.execute(
            select(SSOConfig).where(
                SSOConfig.organization_id == org_id,
                SSOConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="SSO config already exists for this org. Update the existing config.",
            )

        config = SSOConfig(
            organization_id=org_id,
            **data.model_dump(),
            created_by=created_by,
        )
        db.add(config)
        db.flush()

        AuditService(db).write_audit_log(
            action="sso_config.created",
            entity_type="sso_configs",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=config.id,
        )
        return config

    def get_config(self, org_id: uuid.UUID, db: Session) -> SSOConfig:
        config = db.execute(
            select(SSOConfig).where(
                SSOConfig.organization_id == org_id,
                SSOConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO config not found")
        return config

    def update_config(
        self,
        org_id: uuid.UUID,
        config_id: uuid.UUID,
        data: SSOConfigUpdate,
        user_id: uuid.UUID,
        db: Session,
    ) -> SSOConfig:
        config = self._require_config(org_id, config_id, db)
        payload = data.model_dump(exclude_unset=True)
        if not payload:
            return config

        for key, value in payload.items():
            setattr(config, key, value)
        config.updated_at = self.utcnow()
        db.flush()

        AuditService(db).write_audit_log(
            action="sso_config.updated",
            entity_type="sso_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )
        return config

    def activate_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> SSOConfig:
        config = self._require_config(org_id, config_id, db)
        config.is_active = True
        config.updated_at = self.utcnow()
        db.flush()
        AuditService(db).write_audit_log(
            action="sso_config.activated",
            entity_type="sso_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )
        return config

    def deactivate_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> SSOConfig:
        config = self._require_config(org_id, config_id, db)
        config.is_active = False
        config.updated_at = self.utcnow()
        db.flush()
        AuditService(db).write_audit_log(
            action="sso_config.deactivated",
            entity_type="sso_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )
        return config

    def soft_delete_config(self, org_id: uuid.UUID, config_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
        config = self._require_config(org_id, config_id, db)
        now = self.utcnow()
        config.deleted_at = now
        config.is_active = False
        config.updated_at = now
        db.flush()
        AuditService(db).write_audit_log(
            action="sso_config.deleted",
            entity_type="sso_configs",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=config.id,
        )

    def test_config(self, org_id: uuid.UUID, config_id: uuid.UUID, db: Session) -> tuple[bool, list[str]]:
        config = self._require_config(org_id, config_id, db)
        errors: list[str] = []

        if config.entity_id.strip() == "":
            errors.append("entity_id is required")
        if not config.sso_url.startswith(("http://", "https://")):
            errors.append("sso_url must be http(s)")
        cert = config.certificate.strip()
        if "BEGIN CERTIFICATE" not in cert or "END CERTIFICATE" not in cert:
            errors.append("certificate must be PEM formatted")

        return len(errors) == 0, errors

    def _require_config(self, org_id: uuid.UUID, config_id: uuid.UUID, db: Session) -> SSOConfig:
        config = db.execute(
            select(SSOConfig).where(
                SSOConfig.organization_id == org_id,
                SSOConfig.id == config_id,
                SSOConfig.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SSO config not found")
        return config
