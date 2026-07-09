import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission


class RBACService:
    @staticmethod
    def get_user_membership(
        db: Session,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        *,
        active_only: bool = True,
    ) -> Membership | None:
        stmt = select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == organization_id,
        )
        if active_only:
            stmt = stmt.where(Membership.status == "active")
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_role_by_id(db: Session, role_id: uuid.UUID) -> Role | None:
        stmt = select(Role).where(Role.id == role_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_role_by_name(db: Session, organization_id: uuid.UUID, name: str) -> Role | None:
        stmt = select(Role).where(Role.organization_id == organization_id, Role.name == name)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_user_permissions(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> set[str]:
        membership = RBACService.get_user_membership(db, user_id, organization_id, active_only=True)
        if membership is None:
            return set()

        # Join Role and require it to still be active: a deactivated custom role
        # must stop granting permissions on the very next permission check, even
        # though the membership row still points at it (deactivating a role does
        # not, by itself, unassign anyone). Without this, a role deactivation had
        # no real effect on already-assigned members until they were manually
        # reassigned to a different role.
        stmt = (
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .where(RolePermission.role_id == membership.role_id, Role.is_active.is_(True))
        )
        return set(db.execute(stmt).scalars().all())

    @staticmethod
    def user_has_permission(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID, permission_code: str) -> bool:
        return permission_code in RBACService.get_user_permissions(db, user_id, organization_id)

    @staticmethod
    def get_role_permissions(db: Session, role_id: uuid.UUID) -> list[str]:
        stmt = (
            select(Permission.key)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
            .order_by(Permission.key.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def count_active_owners(db: Session, organization_id: uuid.UUID) -> int:
        stmt = (
            select(func.count(Membership.id))
            .join(Role, Role.id == Membership.role_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == "active",
                Role.name == "owner",
            )
        )
        return int(db.execute(stmt).scalar_one())

    @staticmethod
    def assert_not_last_owner_change(
        db: Session,
        *,
        target_membership: Membership,
        organization_id: uuid.UUID,
        new_role_name: str | None = None,
        deactivating: bool = False,
    ) -> None:
        current_role = RBACService.get_role_by_id(db, target_membership.role_id)
        if current_role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current role not found")

        if target_membership.status != "active" or current_role.name != "owner":
            return

        owner_is_being_downgraded = new_role_name is not None and new_role_name != "owner"
        if not owner_is_being_downgraded and not deactivating:
            return

        if RBACService.count_active_owners(db, organization_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change the last active owner membership",
            )
