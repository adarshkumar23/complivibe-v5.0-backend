from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.business_unit import BusinessUnit
from app.models.compliance_policy import CompliancePolicy
from app.models.control import Control
from app.models.risk import Risk
from app.models.vendor import Vendor
from app.services.audit_service import AuditService


class BusinessUnitService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def create_bu(
        self,
        org_id: uuid.UUID,
        name: str,
        code: str,
        parent_bu_id: uuid.UUID | None,
        created_by: uuid.UUID,
        description: str | None = None,
        cost_center: str | None = None,
        bu_lead_user_id: uuid.UUID | None = None,
    ) -> BusinessUnit:
        normalized_code = code.strip().upper()
        if parent_bu_id:
            parent = (
                self.db.query(BusinessUnit)
                .filter(
                    BusinessUnit.id == parent_bu_id,
                    BusinessUnit.organization_id == org_id,
                    BusinessUnit.deleted_at.is_(None),
                )
                .first()
            )
            if not parent:
                raise HTTPException(status_code=404, detail="Parent business unit not found in this organization")

        existing = (
            self.db.query(BusinessUnit)
            .filter(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.code == normalized_code,
                BusinessUnit.deleted_at.is_(None),
            )
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Business unit code '{normalized_code}' already exists in this organization",
            )

        bu = BusinessUnit(
            organization_id=org_id,
            name=name.strip(),
            code=normalized_code,
            parent_bu_id=parent_bu_id,
            description=description,
            cost_center=cost_center,
            bu_lead_user_id=bu_lead_user_id,
            created_by=created_by,
        )
        self.db.add(bu)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="business_unit.created",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=created_by,
            entity_id=bu.id,
        )
        return bu

    def list_bus(self, org_id: uuid.UUID, include_inactive: bool = False) -> list[BusinessUnit]:
        query = self.db.query(BusinessUnit).filter(
            BusinessUnit.organization_id == org_id,
            BusinessUnit.deleted_at.is_(None),
        )
        if not include_inactive:
            query = query.filter(BusinessUnit.is_active.is_(True))
        return query.order_by(BusinessUnit.name.asc()).all()

    def get_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID) -> BusinessUnit:
        bu = (
            self.db.query(BusinessUnit)
            .filter(
                BusinessUnit.id == bu_id,
                BusinessUnit.organization_id == org_id,
                BusinessUnit.deleted_at.is_(None),
            )
            .first()
        )
        if not bu:
            raise HTTPException(status_code=404, detail="Business unit not found")
        return bu

    def get_bu_tree(self, org_id: uuid.UUID) -> list[dict[str, Any]]:
        all_bus = self.list_bus(org_id)
        by_id: dict[uuid.UUID, dict[str, Any]] = {
            bu.id: {"id": str(bu.id), "name": bu.name, "code": bu.code, "children": []} for bu in all_bus
        }

        roots: list[dict[str, Any]] = []
        for bu in all_bus:
            node = by_id[bu.id]
            if bu.parent_bu_id and bu.parent_bu_id in by_id:
                by_id[bu.parent_bu_id]["children"].append(node)
            else:
                roots.append(node)
        return roots

    def update_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID, data: Any, user_id: uuid.UUID) -> BusinessUnit:
        bu = self.get_bu(org_id, bu_id)
        changes = data.model_dump(exclude_unset=True) if hasattr(data, "model_dump") else dict(data or {})
        if not changes:
            return bu

        if "code" in changes and changes["code"] is not None:
            code = str(changes["code"]).strip().upper()
            existing = (
                self.db.query(BusinessUnit)
                .filter(
                    BusinessUnit.organization_id == org_id,
                    BusinessUnit.code == code,
                    BusinessUnit.deleted_at.is_(None),
                    BusinessUnit.id != bu_id,
                )
                .first()
            )
            if existing:
                raise HTTPException(status_code=409, detail=f"Business unit code '{code}' already exists in this organization")
            changes["code"] = code

        if "parent_bu_id" in changes and changes["parent_bu_id"] is not None:
            parent_id = changes["parent_bu_id"]
            if parent_id == bu.id:
                raise HTTPException(status_code=400, detail="Business unit cannot be its own parent")
            parent = (
                self.db.query(BusinessUnit)
                .filter(
                    BusinessUnit.id == parent_id,
                    BusinessUnit.organization_id == org_id,
                    BusinessUnit.deleted_at.is_(None),
                )
                .first()
            )
            if not parent:
                raise HTTPException(status_code=404, detail="Parent business unit not found in this organization")

        for field, value in changes.items():
            if field == "name" and isinstance(value, str):
                value = value.strip()
            setattr(bu, field, value)

        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="business_unit.updated",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=bu.id,
        )
        return bu

    def deactivate_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID, user_id: uuid.UUID) -> BusinessUnit:
        bu = self.get_bu(org_id, bu_id)
        bu.is_active = False
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="business_unit.deactivated",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=bu.id,
        )
        return bu

    def delete_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID, user_id: uuid.UUID) -> BusinessUnit:
        bu = self.get_bu(org_id, bu_id)
        bu.deleted_at = self._now()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="business_unit.deleted",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=bu.id,
        )
        return bu

    def tag_entity(
        self,
        org_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
        business_unit_id: uuid.UUID | None,
        user_id: uuid.UUID,
    ) -> dict[str, str | None]:
        model_map = {
            "risk": Risk,
            "control": Control,
            "policy": CompliancePolicy,
            "vendor": Vendor,
            "ai_system": AISystem,
        }
        model = model_map.get(entity_type)
        if not model:
            raise HTTPException(status_code=400, detail=f"Invalid entity_type: {entity_type}")

        entity = self.db.query(model).filter(model.id == entity_id, model.organization_id == org_id).first()
        if not entity:
            raise HTTPException(status_code=404, detail=f"{entity_type} not found")

        if business_unit_id:
            bu = (
                self.db.query(BusinessUnit)
                .filter(
                    BusinessUnit.id == business_unit_id,
                    BusinessUnit.organization_id == org_id,
                    BusinessUnit.deleted_at.is_(None),
                )
                .first()
            )
            if not bu:
                raise HTTPException(status_code=404, detail="Business unit not found")

        setattr(entity, "business_unit_id", business_unit_id)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="business_unit.entity_tagged",
            entity_type=entity_type,
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=entity_id,
            metadata_json={"business_unit_id": str(business_unit_id) if business_unit_id else None},
        )

        return {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "business_unit_id": str(business_unit_id) if business_unit_id else None,
        }

    def get_bu_summary(self, org_id: uuid.UUID, bu_id: uuid.UUID) -> dict[str, Any]:
        bu = self.get_bu(org_id, bu_id)
        counts = {
            "risks": self.db.query(Risk).filter(Risk.organization_id == org_id, Risk.business_unit_id == bu_id).count(),
            "controls": self.db.query(Control).filter(Control.organization_id == org_id, Control.business_unit_id == bu_id).count(),
            "policies": self.db.query(CompliancePolicy)
            .filter(CompliancePolicy.organization_id == org_id, CompliancePolicy.business_unit_id == bu_id)
            .count(),
            "vendors": self.db.query(Vendor).filter(Vendor.organization_id == org_id, Vendor.business_unit_id == bu_id).count(),
            "ai_systems": self.db.query(AISystem)
            .filter(AISystem.organization_id == org_id, AISystem.business_unit_id == bu_id)
            .count(),
        }
        return {
            "bu_id": str(bu.id),
            "bu_name": bu.name,
            "entity_counts": counts,
            "total_tagged": sum(counts.values()),
        }
