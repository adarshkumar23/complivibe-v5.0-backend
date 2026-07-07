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
from app.models.membership import Membership
from app.models.user import User
from app.services.audit_service import AuditService


class BusinessUnitService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _get_active_children(self, org_id: uuid.UUID, bu_id: uuid.UUID) -> list[BusinessUnit]:
        return (
            self.db.query(BusinessUnit)
            .filter(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.parent_bu_id == bu_id,
                BusinessUnit.deleted_at.is_(None),
                BusinessUnit.is_active.is_(True),
            )
            .all()
        )

    def _assert_would_not_create_cycle(self, org_id: uuid.UUID, bu_id: uuid.UUID, new_parent_id: uuid.UUID) -> None:
        cursor_id: uuid.UUID | None = new_parent_id
        seen: set[uuid.UUID] = set()
        while cursor_id is not None:
            if cursor_id == bu_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot set parent business unit: the chosen parent is a descendant of this business "
                    "unit, which would create a cycle in the hierarchy",
                )
            if cursor_id in seen:
                break
            seen.add(cursor_id)
            cursor = (
                self.db.query(BusinessUnit)
                .filter(BusinessUnit.id == cursor_id, BusinessUnit.organization_id == org_id)
                .first()
            )
            cursor_id = cursor.parent_bu_id if cursor else None

    def _require_active_org_user(self, org_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> User:
        row = (
            self.db.query(User)
            .join(Membership, Membership.user_id == User.id)
            .filter(
                User.id == user_id,
                User.is_active.is_(True),
                User.status == "active",
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
            .first()
        )
        if row is None:
            raise HTTPException(status_code=400, detail=f"{field_name} must be an active organization user")
        return row

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
            if not parent.is_active:
                raise HTTPException(
                    status_code=400,
                    detail=f"Business unit '{parent.name}' ({parent.code}) is inactive and cannot be assigned as a parent",
                )
        if bu_lead_user_id is not None:
            self._require_active_org_user(org_id, bu_lead_user_id, "bu_lead_user_id")

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
            after_json={
                "name": bu.name,
                "code": bu.code,
                "parent_bu_id": str(bu.parent_bu_id) if bu.parent_bu_id else None,
                "is_active": bu.is_active,
            },
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

        before = {
            "name": bu.name,
            "code": bu.code,
            "parent_bu_id": str(bu.parent_bu_id) if bu.parent_bu_id else None,
            "is_active": bu.is_active,
        }

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
        if "bu_lead_user_id" in changes and changes["bu_lead_user_id"] is not None:
            self._require_active_org_user(org_id, changes["bu_lead_user_id"], "bu_lead_user_id")

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
            if not parent.is_active:
                raise HTTPException(
                    status_code=400,
                    detail=f"Business unit '{parent.name}' ({parent.code}) is inactive and cannot be assigned as a parent",
                )
            self._assert_would_not_create_cycle(org_id, bu.id, parent_id)

        activating = changes.get("is_active") is True and not bu.is_active
        deactivating = changes.get("is_active") is False and bu.is_active

        if deactivating:
            active_children = self._get_active_children(org_id, bu.id)
            if active_children:
                names = ", ".join(f"{child.name} ({child.code})" for child in active_children[:5])
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Cannot deactivate business unit '{bu.name}': it still has {len(active_children)} active "
                        f"child business unit(s) ({names}). Deactivate or reparent them first."
                    ),
                )

        if activating:
            effective_parent_id = changes.get("parent_bu_id", bu.parent_bu_id)
            if effective_parent_id:
                parent = (
                    self.db.query(BusinessUnit)
                    .filter(
                        BusinessUnit.id == effective_parent_id,
                        BusinessUnit.organization_id == org_id,
                        BusinessUnit.deleted_at.is_(None),
                    )
                    .first()
                )
                if parent and not parent.is_active:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot reactivate business unit '{bu.name}': its parent "
                        f"'{parent.name}' ({parent.code}) is inactive. Reactivate the parent first.",
                    )

        for field, value in changes.items():
            if field == "name" and isinstance(value, str):
                value = value.strip()
            setattr(bu, field, value)

        self.db.flush()

        after = {
            "name": bu.name,
            "code": bu.code,
            "parent_bu_id": str(bu.parent_bu_id) if bu.parent_bu_id else None,
            "is_active": bu.is_active,
        }
        AuditService(self.db).write_audit_log(
            action="business_unit.updated",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=bu.id,
            before_json=before,
            after_json=after,
        )
        return bu

    def deactivate_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID, user_id: uuid.UUID) -> BusinessUnit:
        bu = self.get_bu(org_id, bu_id)
        if not bu.is_active:
            return bu

        active_children = self._get_active_children(org_id, bu.id)
        if active_children:
            names = ", ".join(f"{child.name} ({child.code})" for child in active_children[:5])
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot deactivate business unit '{bu.name}': it still has {len(active_children)} active "
                    f"child business unit(s) ({names}). Deactivate or reparent them first."
                ),
            )

        bu.is_active = False
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="business_unit.deactivated",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=bu.id,
            before_json={"is_active": True},
            after_json={"is_active": False},
        )
        return bu

    def delete_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID, user_id: uuid.UUID) -> BusinessUnit:
        bu = self.get_bu(org_id, bu_id)

        children = (
            self.db.query(BusinessUnit)
            .filter(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.parent_bu_id == bu_id,
                BusinessUnit.deleted_at.is_(None),
            )
            .all()
        )
        if children:
            names = ", ".join(f"{child.name} ({child.code})" for child in children[:5])
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot delete business unit '{bu.name}': it still has {len(children)} child "
                    f"business unit(s) ({names}). Delete or reparent them first."
                ),
            )

        bu.deleted_at = self._now()
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="business_unit.deleted",
            entity_type="business_units",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=bu.id,
            before_json={"deleted_at": None},
            after_json={"deleted_at": bu.deleted_at.isoformat()},
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
            valid_types = ", ".join(sorted(model_map))
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity_type: '{entity_type}'. Valid options are: {valid_types}",
            )

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

        previous_business_unit_id = getattr(entity, "business_unit_id", None)
        setattr(entity, "business_unit_id", business_unit_id)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="business_unit.entity_tagged",
            entity_type=entity_type,
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=entity_id,
            before_json={"business_unit_id": str(previous_business_unit_id) if previous_business_unit_id else None},
            after_json={"business_unit_id": str(business_unit_id) if business_unit_id else None},
        )

        return {
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "business_unit_id": str(business_unit_id) if business_unit_id else None,
        }

    def business_unit_response_payload(self, org_id: uuid.UUID, bu: BusinessUnit) -> dict[str, Any]:
        total_child_count = (
            self.db.query(BusinessUnit)
            .filter(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.parent_bu_id == bu.id,
                BusinessUnit.deleted_at.is_(None),
            )
            .count()
        )
        active_child_count = (
            self.db.query(BusinessUnit)
            .filter(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.parent_bu_id == bu.id,
                BusinessUnit.deleted_at.is_(None),
                BusinessUnit.is_active.is_(True),
            )
            .count()
        )

        counts = self._entity_counts_for_bu(org_id, bu.id)
        tagged_entity_count = int(sum(int(v) for v in counts.values()))
        context_flags: list[str] = []
        if bu.parent_bu_id is not None:
            parent = (
                self.db.query(BusinessUnit)
                .filter(
                    BusinessUnit.id == bu.parent_bu_id,
                    BusinessUnit.organization_id == org_id,
                    BusinessUnit.deleted_at.is_(None),
                )
                .first()
            )
            if parent is None:
                context_flags.append("parent_missing_or_deleted")
            elif not parent.is_active:
                context_flags.append("parent_inactive")
        if not bu.is_active and tagged_entity_count > 0:
            context_flags.append("inactive_bu_still_tagged_to_entities")
        if active_child_count > 0 and not bu.is_active:
            context_flags.append("inactive_bu_with_active_children")

        payload = {
            "id": bu.id,
            "organization_id": bu.organization_id,
            "name": bu.name,
            "code": bu.code,
            "parent_bu_id": bu.parent_bu_id,
            "description": bu.description,
            "cost_center": bu.cost_center,
            "bu_lead_user_id": bu.bu_lead_user_id,
            "is_active": bu.is_active,
            "created_at": bu.created_at,
            "updated_at": bu.updated_at,
            "deleted_at": bu.deleted_at,
            "active_child_count": active_child_count,
            "total_child_count": total_child_count,
            "tagged_entity_count": tagged_entity_count,
            "context_flags": context_flags,
        }
        return payload

    def get_bu_summary(self, org_id: uuid.UUID, bu_id: uuid.UUID) -> dict[str, Any]:
        bu = self.get_bu(org_id, bu_id)
        counts = self._entity_counts_for_bu(org_id, bu_id)
        return {
            "bu_id": str(bu.id),
            "bu_name": bu.name,
            "is_active": bu.is_active,
            "entity_counts": counts,
            "total_tagged": sum(counts.values()),
            "context_flags": self.business_unit_response_payload(org_id, bu)["context_flags"],
        }

    def _entity_counts_for_bu(self, org_id: uuid.UUID, bu_id: uuid.UUID) -> dict[str, int]:
        return {
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
