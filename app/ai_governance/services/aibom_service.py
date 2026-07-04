import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_governance.services.ai_governance_event_service import AIGovernanceEventService
from app.ai_governance.services.signal_service import SignalService
from app.models.aibom_component import AIBOMComponent
from app.models.aibom_record import AIBOMRecord
from app.models.ai_system import AISystem
from app.services.audit_service import AuditService
from app.core.validation import validate_choice

ALLOWED_COMPONENT_TYPES = {
    "training_data",
    "base_model",
    "fine_tuning_dataset",
    "runtime_data_feed",
    "third_party_api",
    "framework_library",
}


class AIBOMService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_system(self, org_id: uuid.UUID, system_id: uuid.UUID) -> AISystem:
        row = self.db.execute(
            select(AISystem).where(
                AISystem.organization_id == org_id,
                AISystem.id == system_id,
                AISystem.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI system not found")
        return row

    def _require_aibom(self, org_id: uuid.UUID, aibom_id: uuid.UUID) -> AIBOMRecord:
        row = self.db.execute(
            select(AIBOMRecord).where(
                AIBOMRecord.organization_id == org_id,
                AIBOMRecord.id == aibom_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AIBOM record not found")
        return row

    def create_aibom(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        generated_by: uuid.UUID,
        notes: str | None = None,
        components: list | None = None,
    ) -> AIBOMRecord:
        self._require_system(org_id, system_id)
        previous = self.db.execute(
            select(AIBOMRecord)
            .where(
                AIBOMRecord.organization_id == org_id,
                AIBOMRecord.ai_system_id == system_id,
            )
            .order_by(AIBOMRecord.version.desc())
        ).scalars().first()
        next_version = int(previous.version if previous else 0) + 1

        now = self.utcnow()
        row = AIBOMRecord(
            organization_id=org_id,
            ai_system_id=system_id,
            version=next_version,
            generated_at=now,
            generated_by=generated_by,
            notes=notes,
        )
        self.db.add(row)
        self.db.flush()

        copied_components = 0
        explicit_components = components is not None
        source_components = components if explicit_components else self.list_components(org_id, previous.id) if previous else []
        seen_keys: set[tuple[str, str]] = set()
        for component in source_components:
            component_type = validate_choice(component.component_type, ALLOWED_COMPONENT_TYPES, "component_type")
            name = component.name
            key = (component_type, name)
            if key in seen_keys:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Duplicate component in AIBOM version")
            seen_keys.add(key)
            self.db.add(
                AIBOMComponent(
                    organization_id=org_id,
                    aibom_id=row.id,
                    component_type=component_type,
                    name=name,
                    version=component.version,
                    source=component.source,
                    license_type=component.license_type,
                    is_third_party=component.is_third_party,
                    risk_notes=component.risk_notes,
                    source_integration=component.source_integration,
                    created_at=now,
                )
            )
            copied_components += 1
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "aibom.created",
            actor_id=generated_by,
            actor_type="user",
            ai_system_id=system_id,
            event_data={
                "aibom_id": str(row.id),
                "version": row.version,
                "component_count": copied_components,
                "explicit_components": explicit_components,
            },
        )
        AuditService(self.db).write_audit_log(
            action="aibom.created",
            entity_type="aibom_record",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=generated_by,
            after_json={
                "ai_system_id": str(system_id),
                "version": row.version,
                "component_count": copied_components,
                "explicit_components": explicit_components,
            },
            metadata_json={"source": "api"},
        )
        return row

    def get_latest_aibom(self, org_id: uuid.UUID, system_id: uuid.UUID) -> tuple[AIBOMRecord, list[AIBOMComponent]]:
        self._require_system(org_id, system_id)
        row = self.db.execute(
            select(AIBOMRecord)
            .where(
                AIBOMRecord.organization_id == org_id,
                AIBOMRecord.ai_system_id == system_id,
            )
            .order_by(AIBOMRecord.version.desc())
        ).scalars().first()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AIBOM record not found")
        components = self.list_components(org_id, row.id)
        return row, components

    def get_aibom(self, org_id: uuid.UUID, aibom_id: uuid.UUID) -> tuple[AIBOMRecord, list[AIBOMComponent]]:
        row = self._require_aibom(org_id, aibom_id)
        components = self.list_components(org_id, row.id)
        return row, components

    def list_components(self, org_id: uuid.UUID, aibom_id: uuid.UUID) -> list[AIBOMComponent]:
        return self.db.execute(
            select(AIBOMComponent)
            .where(
                AIBOMComponent.organization_id == org_id,
                AIBOMComponent.aibom_id == aibom_id,
            )
            .order_by(AIBOMComponent.component_type.asc(), AIBOMComponent.name.asc())
        ).scalars().all()

    def add_component(self, org_id: uuid.UUID, aibom_id: uuid.UUID, data, user_id: uuid.UUID) -> AIBOMComponent:
        aibom = self._require_aibom(org_id, aibom_id)
        data.component_type = validate_choice(data.component_type, ALLOWED_COMPONENT_TYPES, "component_type")
        existing = self.db.execute(
            select(AIBOMComponent).where(
                AIBOMComponent.organization_id == org_id,
                AIBOMComponent.aibom_id == aibom_id,
                AIBOMComponent.component_type == data.component_type,
                AIBOMComponent.name == data.name,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Component already exists in this AIBOM")

        now = self.utcnow()
        row = AIBOMComponent(
            organization_id=org_id,
            aibom_id=aibom_id,
            component_type=data.component_type,
            name=data.name,
            version=data.version,
            source=data.source,
            license_type=data.license_type,
            is_third_party=data.is_third_party,
            risk_notes=data.risk_notes,
            source_integration=data.source_integration,
            created_at=now,
        )
        self.db.add(row)
        self.db.flush()

        AIGovernanceEventService.log(
            self.db,
            org_id,
            "aibom.component_added",
            actor_id=user_id,
            actor_type="user",
            event_data={"aibom_id": str(aibom_id), "component_type": row.component_type, "name": row.name},
        )
        AuditService(self.db).write_audit_log(
            action="aibom.component_added",
            entity_type="aibom_component",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"aibom_id": str(aibom_id), "component_type": row.component_type, "name": row.name},
            metadata_json={"source": "api"},
        )
        if row.component_type == "training_data":
            SignalService(self.db).emit_signal(
                org_id,
                aibom.ai_system_id,
                signal_type="new_training_data_source",
                description=f"New training data source added: {row.name}",
                actor_id=user_id,
            )
        return row

    @staticmethod
    def diff_aiboms(v1_components: list[AIBOMComponent], v2_components: list[AIBOMComponent]) -> dict:
        v1_keys = {(c.component_type, c.name) for c in v1_components}
        v2_keys = {(c.component_type, c.name) for c in v2_components}
        added = v2_keys - v1_keys
        removed = v1_keys - v2_keys

        changed = []
        for key in v1_keys & v2_keys:
            c1 = next(c for c in v1_components if (c.component_type, c.name) == key)
            c2 = next(c for c in v2_components if (c.component_type, c.name) == key)
            if (
                c1.version != c2.version
                or c1.source != c2.source
                or c1.license_type != c2.license_type
                or c1.is_third_party != c2.is_third_party
                or c1.risk_notes != c2.risk_notes
                or c1.source_integration != c2.source_integration
            ):
                changed.append(
                    {
                        "component_type": key[0],
                        "name": key[1],
                        "from_version": c1.version,
                        "to_version": c2.version,
                        "from_source": c1.source,
                        "to_source": c2.source,
                        "from_license_type": c1.license_type,
                        "to_license_type": c2.license_type,
                        "from_is_third_party": c1.is_third_party,
                        "to_is_third_party": c2.is_third_party,
                        "from_risk_notes": c1.risk_notes,
                        "to_risk_notes": c2.risk_notes,
                        "from_source_integration": c1.source_integration,
                        "to_source_integration": c2.source_integration,
                    }
                )

        return {
            "added": [{"component_type": key[0], "name": key[1]} for key in sorted(added)],
            "removed": [{"component_type": key[0], "name": key[1]} for key in sorted(removed)],
            "changed": sorted(changed, key=lambda item: (item["component_type"], item["name"])),
        }

    def diff_versions(self, org_id: uuid.UUID, system_id: uuid.UUID, v1: int, v2: int) -> dict:
        self._require_system(org_id, system_id)
        aibom_v1 = self.db.execute(
            select(AIBOMRecord).where(
                AIBOMRecord.organization_id == org_id,
                AIBOMRecord.ai_system_id == system_id,
                AIBOMRecord.version == v1,
            )
        ).scalar_one_or_none()
        aibom_v2 = self.db.execute(
            select(AIBOMRecord).where(
                AIBOMRecord.organization_id == org_id,
                AIBOMRecord.ai_system_id == system_id,
                AIBOMRecord.version == v2,
            )
        ).scalar_one_or_none()
        if aibom_v1 is None or aibom_v2 is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AIBOM version not found")

        v1_components = self.list_components(org_id, aibom_v1.id)
        v2_components = self.list_components(org_id, aibom_v2.id)
        return self.diff_aiboms(v1_components, v2_components)

    def sync_components(
        self,
        org_id: uuid.UUID,
        system_id: uuid.UUID,
        components: list[dict],
        source_integration: str,
        generated_by: uuid.UUID,
    ) -> AIBOMRecord:
        aibom = self.create_aibom(
            org_id,
            system_id,
            generated_by,
            notes=f"Synced via {source_integration}",
            components=[],
        )
        for component in components:
            payload = {
                **component,
                "source_integration": component.get("source_integration") or source_integration,
            }
            payload.setdefault("version", None)
            payload.setdefault("source", None)
            payload.setdefault("license_type", None)
            payload.setdefault("risk_notes", None)
            payload.setdefault("is_third_party", False)
            from types import SimpleNamespace

            self.add_component(org_id, aibom.id, SimpleNamespace(**payload), generated_by)
        return aibom
