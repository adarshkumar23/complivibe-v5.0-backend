import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.integrations.mlops.adapter_factory import encrypt_config, get_adapter
from app.ai_governance.services.aibom_service import AIBOMService
from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.ai_system_service import AISystemService
from app.models.ai_system import AISystem
from app.models.mlops_integration import MLOpsIntegration
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_INTEGRATION_TYPES = {"mlflow", "databricks", "sagemaker", "vertex_ai"}
ALLOWED_SYNC_STATUSES = {"success", "failed", "in_progress"}


class MLOPSSyncService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_integration(self, org_id: uuid.UUID, integration_id: uuid.UUID) -> MLOpsIntegration:
        row = self.db.execute(
            select(MLOpsIntegration).where(
                MLOpsIntegration.organization_id == org_id,
                MLOpsIntegration.id == integration_id,
                MLOpsIntegration.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="MLOps integration not found")
        return row

    def create_integration(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> MLOpsIntegration:
        payload = data.model_dump()
        payload["integration_type"] = validate_choice(payload["integration_type"], ALLOWED_INTEGRATION_TYPES, "integration_type")
        now = self.utcnow()
        row = MLOpsIntegration(
            organization_id=org_id,
            integration_type=payload["integration_type"],
            name=payload["name"],
            config_json=encrypt_config(dict(payload["config_json"]), db=self.db, organization_id=org_id),
            last_synced_at=None,
            sync_status=None,
            last_sync_error=None,
            is_active=True,
            created_by=created_by,
            created_at=now,
            updated_at=now,
            deleted_at=None,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "mlops.integration_created",
            actor_id=created_by,
            actor_type="user",
            event_data={"integration_id": str(row.id), "integration_type": row.integration_type},
        )
        AuditService(self.db).write_audit_log(
            action="mlops.integration_created",
            entity_type="mlops_integration",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"integration_type": row.integration_type, "name": row.name, "is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def get_integration(self, org_id: uuid.UUID, integration_id: uuid.UUID) -> MLOpsIntegration:
        return self._require_integration(org_id, integration_id)

    def list_integrations(self, org_id: uuid.UUID) -> list[MLOpsIntegration]:
        return self.db.execute(
            select(MLOpsIntegration)
            .where(
                MLOpsIntegration.organization_id == org_id,
                MLOpsIntegration.deleted_at.is_(None),
            )
            .order_by(MLOpsIntegration.created_at.desc())
        ).scalars().all()

    def list_active_integrations(self) -> list[MLOpsIntegration]:
        return self.db.execute(
            select(MLOpsIntegration).where(
                MLOpsIntegration.deleted_at.is_(None),
                MLOpsIntegration.is_active.is_(True),
            )
        ).scalars().all()

    def update_integration(self, org_id: uuid.UUID, integration_id: uuid.UUID, data) -> MLOpsIntegration:
        row = self._require_integration(org_id, integration_id)
        payload = data.model_dump(exclude_unset=True)
        if "integration_type" in payload:
            payload["integration_type"] = validate_choice(payload["integration_type"], ALLOWED_INTEGRATION_TYPES, "integration_type")
            row.integration_type = payload["integration_type"]
        if "name" in payload and payload["name"] is not None:
            row.name = payload["name"]
        if "is_active" in payload and payload["is_active"] is not None:
            row.is_active = bool(payload["is_active"])
        if "config_json" in payload and payload["config_json"] is not None:
            row.config_json = encrypt_config(
                dict(payload["config_json"]), db=self.db, organization_id=org_id, entity_id=row.id
            )
        row.updated_at = self.utcnow()
        self.db.flush()
        return row

    def deactivate_integration(self, org_id: uuid.UUID, integration_id: uuid.UUID, user_id: uuid.UUID) -> MLOpsIntegration:
        row = self._require_integration(org_id, integration_id)
        row.is_active = False
        row.updated_at = self.utcnow()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="mlops.integration_deactivated",
            entity_type="mlops_integration",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"is_active": row.is_active},
            metadata_json={"source": "api"},
        )
        return row

    def _sync_ai_systems(self, org_id: uuid.UUID, models: list[dict], triggered_by: uuid.UUID) -> int:
        created_systems = 0
        ai_system_service = AISystemService(self.db)
        for model in models:
            existing = self.db.execute(
                select(AISystem).where(
                    AISystem.organization_id == org_id,
                    AISystem.name == model["name"],
                    AISystem.system_type == "model",
                    AISystem.deleted_at.is_(None),
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            payload = SimpleNamespace(
                name=model["name"],
                system_type="model",
                description=model.get("description", ""),
                owner_id=triggered_by,
                vendor_id=None,
                deployment_status="production" if model.get("stage") == "Production" else "development",
                risk_tier="unassessed",
                data_sources_description=None,
                purpose="ML model synced from MLOps integration",
                affected_population=None,
                geographic_scope=None,
            )
            ai_system_service.create_system(org_id=org_id, data=payload, created_by=triggered_by)
            created_systems += 1
        return created_systems

    def sync(
        self,
        org_id: uuid.UUID,
        integration_id: uuid.UUID,
        triggered_by: uuid.UUID,
        *,
        raise_on_error: bool = True,
    ) -> dict:
        integration = self._require_integration(org_id, integration_id)
        if not integration.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Integration is inactive")

        integration.sync_status = "in_progress"
        integration.updated_at = self.utcnow()
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "mlops.sync_triggered",
            actor_id=triggered_by,
            actor_type="user",
            event_data={"integration_id": str(integration.id)},
        )
        AuditService(self.db).write_audit_log(
            action="mlops.sync_triggered",
            entity_type="mlops_integration",
            entity_id=integration.id,
            organization_id=org_id,
            actor_user_id=triggered_by,
            after_json={"sync_status": integration.sync_status},
            metadata_json={"source": "service"},
        )

        try:
            adapter = get_adapter(integration, db=self.db)
            models = adapter.fetch_registered_models()
            components = adapter.map_to_aibom_components(models)

            created_systems = self._sync_ai_systems(org_id, models, triggered_by)

            updated_aiboms = 0
            system_ids = self.db.execute(
                select(AISystem.id).where(
                    AISystem.organization_id == org_id,
                    AISystem.system_type == "model",
                    AISystem.deleted_at.is_(None),
                )
            ).scalars().all()
            if system_ids and components:
                AIBOMService(self.db).sync_components(
                    org_id=org_id,
                    system_id=system_ids[0],
                    components=components,
                    source_integration="mlflow",
                    generated_by=triggered_by,
                )
                updated_aiboms += 1

            integration.last_synced_at = self.utcnow()
            integration.sync_status = "success"
            integration.last_sync_error = None
            integration.updated_at = self.utcnow()
            self.db.flush()

            result = {
                "models_found": len(models),
                "systems_created": created_systems,
                "aiboms_updated": updated_aiboms,
            }
            AIGovernanceEventService.log(
                self.db,
                org_id,
                "mlops.sync_completed",
                actor_id=triggered_by,
                actor_type="user",
                event_data={"integration_id": str(integration.id), **result},
            )
            AuditService(self.db).write_audit_log(
                action="mlops.sync_completed",
                entity_type="mlops_integration",
                entity_id=integration.id,
                organization_id=org_id,
                actor_user_id=triggered_by,
                after_json=result,
                metadata_json={"source": "service"},
            )
            return result
        except Exception as exc:
            integration.sync_status = "failed"
            integration.last_sync_error = str(exc)[:1000]
            integration.updated_at = self.utcnow()
            self.db.flush()

            AIGovernanceEventService.log(
                self.db,
                org_id,
                "mlops.sync_failed",
                actor_id=triggered_by,
                actor_type="user",
                event_data={"integration_id": str(integration.id), "error": integration.last_sync_error},
            )
            AuditService(self.db).write_audit_log(
                action="mlops.sync_failed",
                entity_type="mlops_integration",
                entity_id=integration.id,
                organization_id=org_id,
                actor_user_id=triggered_by,
                after_json={"error": integration.last_sync_error},
                metadata_json={"source": "service"},
            )
            if raise_on_error:
                raise
            return {
                "error": integration.last_sync_error,
                "models_found": 0,
                "systems_created": 0,
                "aiboms_updated": 0,
            }

    def get_sync_log(self, org_id: uuid.UUID, integration_id: uuid.UUID) -> MLOpsIntegration:
        row = self._require_integration(org_id, integration_id)
        if row.sync_status is not None and row.sync_status not in ALLOWED_SYNC_STATUSES:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid integration sync status")
        return row


def run_daily_mlops_sync_sweep(db: Session) -> dict:
    service = MLOPSSyncService(db)
    integrations = service.list_active_integrations()
    synced = 0
    failed = 0
    for integration in integrations:
        try:
            service.sync(
                org_id=integration.organization_id,
                integration_id=integration.id,
                triggered_by=integration.created_by,
            )
            synced += 1
        except Exception:
            failed += 1
    return {
        "integrations_processed": len(integrations),
        "synced": synced,
        "failed": failed,
        "records_processed": len(integrations),
    }
