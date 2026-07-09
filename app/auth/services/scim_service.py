from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.compliance.services.offboarding_service import OffboardingService
from app.models.membership import Membership
from app.models.role import Role
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.seed_service import SeedService


class SCIMService:
    @staticmethod
    def org_users_query(org_id: uuid.UUID):
        """Base query for all users belonging to an organization (via membership).

        Shared by the SCIM user-listing endpoint and any other endpoint (e.g.
        `GET /api/v1/users`) that needs the same underlying org-scoped user
        data, so both stay in sync with a single source of truth.
        """
        return (
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == org_id)
            .order_by(User.created_at.asc())
        )

    def list_users(
        self,
        org_id: uuid.UUID,
        start_index: int = 1,
        count: int = 100,
        filter_str: str | None = None,
        db: Session | None = None,
    ) -> dict:
        if db is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database session required")
        normalized_start = max(1, int(start_index))
        normalized_count = max(1, min(int(count), 200))

        query = (
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(Membership.organization_id == org_id)
            .order_by(User.created_at.asc())
        )
        if filter_str and "userName eq" in filter_str:
            parts = filter_str.split('"')
            if len(parts) >= 2:
                email = parts[1].strip().lower()
                query = query.where(User.email == email)

        rows = list(db.execute(query).all())
        total = len(rows)
        paged = rows[normalized_start - 1 : normalized_start - 1 + normalized_count]

        return {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": total,
            "startIndex": normalized_start,
            "itemsPerPage": len(paged),
            "Resources": [self._to_scim_user(user, active=self._scim_active(user, membership)) for user, membership in paged],
        }

    def get_user(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> dict:
        user, membership = self._get_org_user_with_membership(org_id, user_id, db)
        return self._to_scim_user(user, active=self._scim_active(user, membership))

    def provision_user(self, org_id: uuid.UUID, scim_payload: dict, db: Session) -> dict:
        email = str(scim_payload.get("userName") or "").strip().lower()
        if not email:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="userName is required")

        name = scim_payload.get("name") or {}
        given = str(name.get("givenName") or "").strip()
        family = str(name.get("familyName") or "").strip()
        full_name = f"{given} {family}".strip()
        is_active = bool(scim_payload.get("active", True))

        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            membership = db.execute(
                select(Membership).where(
                    Membership.user_id == existing.id,
                    Membership.organization_id == org_id,
                )
            ).scalar_one_or_none()
            if membership is None:
                membership = self._create_membership(existing.id, org_id, role_name="member", db=db)
            self._set_membership_active(existing, membership, is_active, db)
            if full_name:
                existing.full_name = full_name
            db.flush()
            return self._to_scim_user(existing, active=self._scim_active(existing, membership))

        user = User(
            email=email,
            full_name=full_name or email,
            hashed_password=f"!{secrets.token_hex(32)}",
            status="active" if is_active else "inactive",
            is_active=is_active,
            is_superuser=False,
        )
        db.add(user)
        db.flush()
        self._create_membership(user.id, org_id, role_name="member", db=db)

        AuditService(db).write_audit_log(
            action="user.provisioned_via_scim",
            entity_type="users",
            organization_id=org_id,
            actor_user_id=user.id,
            entity_id=user.id,
            metadata_json={"source": "scim", "external_id": scim_payload.get("externalId")},
        )
        db.flush()
        membership = self._get_org_membership(org_id, user.id, db)
        return self._to_scim_user(user, active=self._scim_active(user, membership))

    def update_user(self, org_id: uuid.UUID, user_id: uuid.UUID, scim_payload: dict, db: Session) -> dict:
        user, membership = self._get_org_user_with_membership(org_id, user_id, db)
        name = scim_payload.get("name") or {}
        given = str(name.get("givenName") or "").strip()
        family = str(name.get("familyName") or "").strip()
        full_name = f"{given} {family}".strip()

        if full_name:
            user.full_name = full_name
        if "active" in scim_payload:
            self._set_membership_active(user, membership, bool(scim_payload["active"]), db)

        AuditService(db).write_audit_log(
            action="user.updated_via_scim",
            entity_type="users",
            organization_id=org_id,
            actor_user_id=user.id,
            entity_id=user.id,
        )
        db.flush()
        return self._to_scim_user(user, active=self._scim_active(user, membership))

    def patch_user(self, org_id: uuid.UUID, user_id: uuid.UUID, operations: list[dict], db: Session) -> dict:
        user, membership = self._get_org_user_with_membership(org_id, user_id, db)

        for operation in operations:
            op_type = str(operation.get("op") or "").lower()
            path = str(operation.get("path") or "")
            value = operation.get("value")
            if op_type != "replace":
                continue
            if path == "active":
                self._set_membership_active(user, membership, bool(value), db)
            elif path == "name.givenName":
                family = self._split_name(user.full_name)[1]
                user.full_name = f"{value or ''} {family}".strip()
            elif path == "name.familyName":
                given = self._split_name(user.full_name)[0]
                user.full_name = f"{given} {value or ''}".strip()

        AuditService(db).write_audit_log(
            action="user.patched_via_scim",
            entity_type="users",
            organization_id=org_id,
            actor_user_id=user.id,
            entity_id=user.id,
            metadata_json={"operations": operations},
        )
        db.flush()
        return self._to_scim_user(user, active=self._scim_active(user, membership))

    def deprovision_user(self, org_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> None:
        user, membership = self._get_org_user_with_membership(org_id, user_id, db)
        self._set_membership_active(user, membership, False, db)

        try:
            successor_id = self._find_successor(org_id, user_id, db)
            if successor_id is not None:
                OffboardingService(db).run_offboarding(
                    org_id=org_id,
                    deactivated_user_id=user_id,
                    successor_id=successor_id,
                    executed_by=user_id,
                )
        except Exception:
            pass

        AuditService(db).write_audit_log(
            action="user.deprovisioned_via_scim",
            entity_type="users",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=user_id,
            metadata_json={"source": "scim"},
        )
        db.flush()

    @staticmethod
    def _to_scim_user(user: User, *, active: bool | None = None) -> dict:
        given, family = SCIMService._split_name(user.full_name)
        return {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "id": str(user.id),
            "userName": user.email,
            "name": {
                "givenName": given,
                "familyName": family,
                "formatted": user.full_name or user.email,
            },
            "emails": [{"value": user.email, "primary": True}],
            "active": user.is_active if active is None else active,
            "meta": {
                "resourceType": "User",
                "created": user.created_at.isoformat(),
                "lastModified": user.updated_at.isoformat(),
            },
        }

    @staticmethod
    def _split_name(full_name: str | None) -> tuple[str, str]:
        parts = (full_name or "").split()
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])

    @staticmethod
    def _get_org_user(org_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> User:
        user, _ = SCIMService._get_org_user_with_membership(org_id, user_id, db)
        return user

    @staticmethod
    def _get_org_user_with_membership(org_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> tuple[User, Membership]:
        row = db.execute(
            select(User, Membership)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == user_id,
                Membership.organization_id == org_id,
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found in this organization")
        return row

    @staticmethod
    def _get_org_membership(org_id: uuid.UUID, user_id: uuid.UUID, db: Session) -> Membership:
        membership = db.execute(
            select(Membership).where(Membership.organization_id == org_id, Membership.user_id == user_id)
        ).scalar_one()
        return membership

    @staticmethod
    def _scim_active(user: User, membership: Membership) -> bool:
        return user.is_active and user.status == "active" and membership.status == "active"

    @staticmethod
    def _set_membership_active(user: User, membership: Membership, is_active: bool, db: Session) -> None:
        membership.status = "active" if is_active else "inactive"
        if is_active:
            user.is_active = True
            user.status = "active"
            return

        other_active_memberships = db.execute(
            select(func.count(Membership.id)).where(
                Membership.user_id == user.id,
                Membership.organization_id != membership.organization_id,
                Membership.status == "active",
            )
        ).scalar_one()
        if other_active_memberships == 0:
            user.is_active = False
            user.status = "inactive"

    @staticmethod
    def _create_membership(user_id: uuid.UUID, org_id: uuid.UUID, role_name: str, db: Session) -> Membership:
        roles = SeedService.ensure_roles_for_organization(db, org_id)
        candidates = [role_name]
        if role_name == "member":
            candidates.extend(["reviewer", "compliance_manager", "admin", "owner", "auditor"])
        role = None
        for candidate in candidates:
            if candidate in roles:
                role = roles[candidate]
                break
        if role is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Role not available")

        membership = Membership(
            organization_id=org_id,
            user_id=user_id,
            role_id=role.id,
            status="active",
            invited_by=None,
        )
        db.add(membership)
        db.flush()
        return membership

    @staticmethod
    def _find_successor(org_id: uuid.UUID, excluded_user_id: uuid.UUID, db: Session) -> uuid.UUID | None:
        row = db.execute(
            select(Membership.user_id)
            .join(Role, Role.id == Membership.role_id)
            .join(User, User.id == Membership.user_id)
            .where(
                Membership.organization_id == org_id,
                Membership.user_id != excluded_user_id,
                Membership.status == "active",
                User.is_active.is_(True),
                User.status == "active",
                Role.name.in_(("owner", "admin")),
            )
            .order_by(User.created_at.asc())
        ).first()
        if row is None:
            return None
        return row[0]

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)
