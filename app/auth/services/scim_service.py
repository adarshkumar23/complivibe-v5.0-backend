from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


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

        # Tenant guard: resolve an existing user ONLY within THIS org's membership
        # (the same join used by _get_org_user_with_membership and by the router's own
        # status-code lookup). A SCIM token must never resolve, mutate, or absorb a
        # user who belongs to another organization.
        existing = db.execute(
            select(User)
            .join(Membership, Membership.user_id == User.id)
            .where(User.email == email, Membership.organization_id == org_id)
        ).scalar_one_or_none()
        if existing is not None:
            membership = self._get_org_membership(org_id, existing.id, db)
            was_active = self._scim_active(existing, membership)
            was_named = existing.full_name
            self._set_membership_active(existing, membership, is_active, db)
            if full_name:
                # Safe: `existing` is a member of THIS org. update_user / patch_user are
                # likewise org-scoped, so a foreign tenant's token can never reach here
                # to overwrite the shared User.full_name.
                existing.full_name = full_name
            db.flush()
            now_active = self._scim_active(existing, membership)

            # An IdP-driven reactivate/deactivate/rename of someone who is already a
            # member. There is no interactive actor to ask afterwards, so record the
            # before/after explicitly -- symmetric with deprovision_user, which has
            # always been audited.
            AuditService(db).write_audit_log(
                action="user.reprovisioned_via_scim",
                entity_type="users",
                organization_id=org_id,
                actor_user_id=existing.id,
                entity_id=existing.id,
                before_json={"active": was_active, "full_name": was_named},
                after_json={"active": now_active, "full_name": existing.full_name},
                metadata_json={"source": "scim", "external_id": scim_payload.get("externalId")},
            )
            db.flush()
            return self._to_scim_user(existing, active=now_active)

        # Not a member of this org. Because User.email is globally unique, an email that
        # already exists must belong to another tenant's user -- refuse rather than
        # absorb it into this org, reactivate its global account, or rename it.
        if db.execute(select(User.id).where(User.email == email)).scalar_one_or_none() is not None:
            # A tenant-boundary probe: this org's IdP token asked for a user that
            # belongs to someone else. The rejection IS the security event, so record
            # it against the ATTEMPTING org before unwinding. The commit is deliberate:
            # raising below aborts the request, and an audit row that rolls back with
            # the rejection would leave no trace of the attempt at all. Only SELECTs
            # have run on this path, so there is nothing else to make durable.
            #
            # No entity_id -- the target user is deliberately never resolved for this
            # caller, and naming it here would leak another tenant's user id into an
            # org-readable trail. The attempted email is already known to the caller.
            AuditService(db).write_audit_log(
                action="user.scim_cross_tenant_provision_rejected",
                entity_type="users",
                organization_id=org_id,
                metadata_json={
                    "source": "scim",
                    "attempted_email": email,
                    "external_id": scim_payload.get("externalId"),
                    "outcome": "rejected_409",
                },
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists in another organization and cannot be provisioned here",
            )

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

        # The deactivation above is the security-critical part of deprovisioning and
        # must persist even if the (secondary) offboarding automation fails. But a
        # failed offboarding must be recorded honestly -- never masked behind a clean
        # "deprovisioned" audit log -- so the trail cannot assert success that did not
        # happen.
        offboarding_status = "not_applicable"
        try:
            successor_id = self._find_successor(org_id, user_id, db)
            if successor_id is not None:
                OffboardingService(db).run_offboarding(
                    org_id=org_id,
                    deactivated_user_id=user_id,
                    successor_id=successor_id,
                    executed_by=user_id,
                )
                offboarding_status = "completed"
        except Exception as exc:  # noqa: BLE001 - deactivation must persist; failure is recorded, not swallowed
            offboarding_status = "failed"
            logger.exception(
                "SCIM offboarding automation failed for user %s in org %s after deactivation",
                user_id,
                org_id,
            )
            AuditService(db).write_audit_log(
                action="user.scim_offboarding_failed",
                entity_type="users",
                organization_id=org_id,
                actor_user_id=user_id,
                entity_id=user_id,
                metadata_json={"source": "scim", "error": str(exc)},
            )

        AuditService(db).write_audit_log(
            action="user.deprovisioned_via_scim",
            entity_type="users",
            organization_id=org_id,
            actor_user_id=user_id,
            entity_id=user_id,
            metadata_json={"source": "scim", "offboarding_status": offboarding_status},
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
        # Set THIS org's membership state, then recompute the shared User.is_active/status
        # SYMMETRICALLY from all memberships -- never unconditionally force the global
        # flag from one tenant's token. The user is active iff this membership is now
        # active OR another org still has them active. (Deactivation and activation are
        # handled by the same rule, so an org's SCIM token cannot flip the global account
        # state on the strength of its own membership alone.)
        membership.status = "active" if is_active else "inactive"

        other_active_memberships = db.execute(
            select(func.count(Membership.id)).where(
                Membership.user_id == user.id,
                Membership.organization_id != membership.organization_id,
                Membership.status == "active",
            )
        ).scalar_one()
        has_any_active = is_active or other_active_memberships > 0
        user.is_active = has_any_active
        user.status = "active" if has_any_active else "inactive"

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
