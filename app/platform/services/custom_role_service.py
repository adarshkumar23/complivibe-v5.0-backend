from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.services.audit_service import AuditService
from app.services.rbac_service import RBACService


class CustomRoleService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _valid_permission_keys(self) -> set[str]:
        return set(self.db.execute(select(Permission.key)).scalars().all())

    def _validate_permission_codes(self, permission_codes: list[str]) -> list[str]:
        normalized = sorted({code.strip() for code in permission_codes if code and code.strip()})
        if not normalized:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="permission_codes cannot be empty")
        valid = self._valid_permission_keys()
        invalid = sorted(set(normalized) - valid)
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid permission_codes: {', '.join(invalid)}",
            )
        return normalized

    def _require_role(self, org_id: uuid.UUID, role_id: uuid.UUID) -> Role:
        role = self.db.execute(select(Role).where(Role.id == role_id)).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        if role.organization_id not in {org_id, None}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        return role

    def _set_role_permissions(self, role_id: uuid.UUID, permission_codes: list[str]) -> None:
        normalized = self._validate_permission_codes(permission_codes)
        permissions = self.db.execute(select(Permission).where(Permission.key.in_(normalized))).scalars().all()
        permission_ids = {p.id for p in permissions}

        existing = self.db.execute(select(RolePermission).where(RolePermission.role_id == role_id)).scalars().all()
        for row in existing:
            if row.permission_id not in permission_ids:
                self.db.delete(row)

        existing_ids = {row.permission_id for row in existing}
        for permission in permissions:
            if permission.id not in existing_ids:
                self.db.add(RolePermission(role_id=role_id, permission_id=permission.id))

    def create_custom_role(
        self,
        org_id: uuid.UUID,
        name: str,
        description: str | None,
        permission_codes: list[str],
        created_by: uuid.UUID,
    ) -> Role:
        normalized_permission_codes = self._validate_permission_codes(permission_codes)
        existing = self.db.execute(
            select(Role).where(
                Role.organization_id == org_id,
                func.lower(Role.name) == name.strip().lower(),
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists in organization")

        role = Role(
            organization_id=org_id,
            name=name.strip(),
            description=description,
            is_system=False,
            is_system_role=False,
            is_active=True,
        )
        self.db.add(role)
        self.db.flush()
        self._set_role_permissions(role.id, normalized_permission_codes)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="custom_role.created",
            entity_type="role",
            entity_id=role.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={"name": role.name, "permission_codes": normalized_permission_codes},
            metadata_json={"source": "api"},
        )
        return role

    def update_custom_role(
        self,
        org_id: uuid.UUID,
        role_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        permission_codes: list[str] | None = None,
        updated_by: uuid.UUID | None = None,
    ) -> Role:
        role = self._require_role(org_id, role_id)
        if role.is_system_role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System roles cannot be edited")
        if role.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        if name is not None:
            candidate_name = name.strip()
            duplicate = self.db.execute(
                select(Role).where(
                    Role.organization_id == org_id,
                    Role.id != role_id,
                    func.lower(Role.name) == candidate_name.lower(),
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists in organization")
            role.name = candidate_name
        if description is not None:
            role.description = description
        if permission_codes is not None:
            current_permissions = RBACService.get_role_permissions(self.db, role.id)
            self._set_role_permissions(role.id, permission_codes)
        else:
            current_permissions = None

        self.db.flush()
        before_json: dict[str, object] = {"permission_codes": current_permissions}
        if name is not None:
            before_json["name"] = name
        if description is not None:
            before_json["description"] = description
        AuditService(self.db).write_audit_log(
            action="custom_role.updated",
            entity_type="role",
            entity_id=role.id,
            organization_id=org_id,
            actor_user_id=updated_by,
            before_json=before_json,
            after_json={
                "name": role.name,
                "description": role.description,
                "permission_codes": RBACService.get_role_permissions(self.db, role.id),
            },
            metadata_json={"source": "api"},
        )
        return role

    def deactivate_custom_role(self, org_id: uuid.UUID, role_id: uuid.UUID, deactivated_by: uuid.UUID) -> Role:
        role = self._require_role(org_id, role_id)
        if role.is_system_role:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System roles cannot be deactivated")
        if role.organization_id != org_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        active_assignments = int(
            self.db.execute(
                select(func.count(Membership.id)).where(
                    Membership.organization_id == org_id,
                    Membership.role_id == role.id,
                    Membership.status == "active",
                )
            ).scalar_one()
        )
        if active_assignments > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Role has {active_assignments} active membership assignment(s); reassign members before deactivation",
            )

        role.is_active = False
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="custom_role.deactivated",
            entity_type="role",
            entity_id=role.id,
            organization_id=org_id,
            actor_user_id=deactivated_by,
            after_json={"is_active": role.is_active},
            metadata_json={"source": "api"},
        )
        return role

    def assign_role_to_membership(
        self,
        org_id: uuid.UUID,
        membership_id: uuid.UUID,
        role_id: uuid.UUID,
        assigned_by: uuid.UUID,
    ) -> Membership:
        membership = self.db.execute(
            select(Membership).where(
                Membership.id == membership_id,
                Membership.organization_id == org_id,
            )
        ).scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

        role = self._require_role(org_id, role_id)
        if not role.is_active:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role is inactive")
        if role.organization_id not in {org_id, None}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

        previous_role_id = membership.role_id
        previous_role_name = None
        if previous_role_id is not None:
            prev_role = self.db.execute(select(Role).where(Role.id == previous_role_id)).scalar_one_or_none()
            if prev_role is not None:
                previous_role_name = prev_role.name

        membership.role_id = role.id
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="custom_role.assigned",
            entity_type="membership",
            entity_id=membership.id,
            organization_id=org_id,
            actor_user_id=assigned_by,
            before_json={
                "role_id": str(previous_role_id) if previous_role_id is not None else None,
                "role_name": previous_role_name,
            },
            after_json={"role_id": str(role.id), "role_name": role.name},
            metadata_json={"source": "api"},
        )
        return membership

    def list_roles(self, org_id: uuid.UUID, *, include_system: bool = True, include_custom: bool = True) -> list[Role]:
        stmt = select(Role).where(Role.is_active.is_(True))
        if include_system and include_custom:
            stmt = stmt.where(or_(Role.organization_id == org_id, and_(Role.organization_id.is_(None), Role.is_system_role.is_(True))))
        elif include_system:
            stmt = stmt.where(
                or_(
                    and_(Role.organization_id == org_id, Role.is_system_role.is_(True)),
                    and_(Role.organization_id.is_(None), Role.is_system_role.is_(True)),
                )
            )
        elif include_custom:
            stmt = stmt.where(
                Role.organization_id == org_id,
                Role.is_system_role.is_(False),
            )
        else:
            return []
        return list(self.db.execute(stmt.order_by(Role.is_system_role.desc(), Role.name.asc())).scalars().all())

    def get_role_permissions(self, org_id: uuid.UUID, role_id: uuid.UUID) -> list[str]:
        _ = self._require_role(org_id, role_id)
        return RBACService.get_role_permissions(self.db, role_id)
