import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.membership import Membership
from app.models.non_human_identity import NonHumanIdentity
from app.models.user import User
from app.services.audit_service import AuditService

TERMINAL_STATUS = "deleted"


class NonHumanIdentityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def require_identity_in_org(self, organization_id: uuid.UUID, identity_id: uuid.UUID) -> NonHumanIdentity:
        row = self.db.execute(
            select(NonHumanIdentity).where(
                NonHumanIdentity.id == identity_id,
                NonHumanIdentity.organization_id == organization_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Non-human identity not found")
        return row

    def ensure_owner_is_active_member(self, organization_id: uuid.UUID, owner_user_id: uuid.UUID) -> User:
        membership = self.db.execute(
            select(Membership).where(
                Membership.organization_id == organization_id,
                Membership.user_id == owner_user_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        user = self.db.execute(select(User).where(User.id == owner_user_id)).scalar_one_or_none()
        if membership is None or user is None or not user.is_active or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="owner_user_id must be an active member of the organization",
            )
        return user

    @staticmethod
    def _snapshot(row: NonHumanIdentity) -> dict[str, Any]:
        return {
            "name": row.name,
            "identity_type": row.identity_type,
            "owner_user_id": str(row.owner_user_id),
            "status": row.status,
            "is_active": row.is_active,
            "is_orphaned": row.is_orphaned,
            "risk_level": row.risk_level,
            "rotation_due_at": row.rotation_due_at.isoformat() if row.rotation_due_at else None,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        }

    def _write_audit(
        self,
        *,
        action: str,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        entity_id: uuid.UUID | None = None,
        before_json: dict | None = None,
        after_json: dict | None = None,
        metadata_json: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        AuditService(self.db).write_audit_log(
            action=action,
            entity_type="non_human_identity",
            entity_id=entity_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            before_json=before_json,
            after_json=after_json,
            metadata_json=metadata_json or {"source": "api"},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def list_identities(
        self,
        organization_id: uuid.UUID,
        *,
        status_value: str | None = None,
        identity_type: str | None = None,
        owner_user_id: uuid.UUID | None = None,
        active_only: bool | None = None,
        include_deleted: bool = False,
    ) -> list[NonHumanIdentity]:
        stmt = select(NonHumanIdentity).where(NonHumanIdentity.organization_id == organization_id)
        if not include_deleted:
            stmt = stmt.where(NonHumanIdentity.status != TERMINAL_STATUS)
        if status_value is not None:
            stmt = stmt.where(NonHumanIdentity.status == status_value)
        if identity_type is not None:
            stmt = stmt.where(NonHumanIdentity.identity_type == identity_type)
        if owner_user_id is not None:
            stmt = stmt.where(NonHumanIdentity.owner_user_id == owner_user_id)
        if active_only is not None:
            stmt = stmt.where(NonHumanIdentity.is_active.is_(active_only))
        rows = self.db.execute(stmt.order_by(NonHumanIdentity.created_at.desc())).scalars().all()
        return list(rows)

    def create_identity(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        data: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NonHumanIdentity:
        self.ensure_owner_is_active_member(organization_id, data["owner_user_id"])
        if data.get("status") == TERMINAL_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New identities cannot start as deleted")

        row = NonHumanIdentity(organization_id=organization_id, created_by_user_id=actor_user_id, **data)
        if row.status == "inactive":
            row.is_active = False
        if row.status == "orphaned":
            row.is_orphaned = True
            row.orphan_detected_at = self.utcnow()
            row.risk_level = row.risk_level if row.risk_level in {"high", "critical"} else "high"
        self.db.add(row)
        self.db.flush()
        self._write_audit(
            action="non_human_identity.created",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            after_json=self._snapshot(row),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return row

    def update_identity(
        self,
        *,
        organization_id: uuid.UUID,
        identity_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        changes: dict[str, Any],
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NonHumanIdentity:
        row = self.require_identity_in_org(organization_id, identity_id)
        if row.status == TERMINAL_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deleted identities cannot be updated")
        if changes.get("status") == TERMINAL_STATUS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Use delete endpoint to soft delete identities")
        if "owner_user_id" in changes and changes["owner_user_id"] is not None:
            self.ensure_owner_is_active_member(organization_id, changes["owner_user_id"])

        before = self._snapshot(row)
        for field, value in changes.items():
            setattr(row, field, value)

        if "owner_user_id" in changes:
            row.is_orphaned = False
            row.orphan_detected_at = None
            if row.status == "orphaned":
                row.status = "active"
            if row.risk_reason == "Owner user is inactive or deactivated":
                row.risk_reason = None
            if row.risk_level == "high":
                row.risk_level = "low"
        if row.status == "inactive":
            row.is_active = False
        elif row.status == "active":
            row.is_active = True
            row.is_orphaned = False
            row.orphan_detected_at = None
        elif row.status == "orphaned":
            row.is_active = True
            row.is_orphaned = True
            row.orphan_detected_at = row.orphan_detected_at or self.utcnow()
            row.risk_level = row.risk_level if row.risk_level in {"high", "critical"} else "high"

        self.db.flush()
        self._write_audit(
            action="non_human_identity.updated",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            before_json=before,
            after_json=self._snapshot(row),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return row

    def soft_delete_identity(
        self,
        *,
        organization_id: uuid.UUID,
        identity_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NonHumanIdentity:
        row = self.require_identity_in_org(organization_id, identity_id)
        if row.status == TERMINAL_STATUS:
            return row
        before = self._snapshot(row)
        row.status = TERMINAL_STATUS
        row.is_active = False
        row.deleted_at = self.utcnow()
        row.deleted_by_user_id = actor_user_id
        self.db.flush()
        self._write_audit(
            action="non_human_identity.deleted",
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            entity_id=row.id,
            before_json=before,
            after_json=self._snapshot(row),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return row

    def flag_orphaned_identities(
        self,
        *,
        organization_id: uuid.UUID,
        actor_user_id: uuid.UUID | None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, int]:
        rows = self.db.execute(
            select(NonHumanIdentity)
            .join(User, User.id == NonHumanIdentity.owner_user_id)
            .where(
                NonHumanIdentity.organization_id == organization_id,
                NonHumanIdentity.is_active.is_(True),
                NonHumanIdentity.status != TERMINAL_STATUS,
                or_(User.is_active.is_(False), User.status != "active"),
            )
        ).scalars().all()

        flagged = 0
        already = 0
        now = self.utcnow()
        for row in rows:
            if row.is_orphaned and row.status == "orphaned":
                already += 1
                continue
            before = self._snapshot(row)
            row.is_orphaned = True
            row.orphan_detected_at = row.orphan_detected_at or now
            row.status = "orphaned"
            row.risk_level = row.risk_level if row.risk_level == "critical" else "high"
            row.risk_reason = "Owner user is inactive or deactivated"
            self.db.flush()
            self._write_audit(
                action="non_human_identity.orphaned_flagged",
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                entity_id=row.id,
                before_json=before,
                after_json=self._snapshot(row),
                metadata_json={"source": "orphan_scan"},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            flagged += 1

        return {"identities_scanned": len(rows), "orphaned_flagged": flagged, "already_orphaned": already}

    def summary(self, organization_id: uuid.UUID, *, stale_days: int = 90) -> dict[str, int | dict[str, int]]:
        now = self.utcnow()
        stale_before = now - timedelta(days=stale_days)
        base_filters = (NonHumanIdentity.organization_id == organization_id, NonHumanIdentity.status != TERMINAL_STATUS)
        active_filters = (*base_filters, NonHumanIdentity.is_active.is_(True))

        def count_where(*filters: Any) -> int:
            return int(self.db.execute(select(func.count(NonHumanIdentity.id)).where(*filters)).scalar_one())

        stale_count = count_where(
            *active_filters,
            or_(NonHumanIdentity.last_used_at.is_(None), NonHumanIdentity.last_used_at < stale_before),
        )
        unrotated_count = count_where(
            *active_filters,
            NonHumanIdentity.rotation_due_at.is_not(None),
            NonHumanIdentity.rotation_due_at <= now,
        )
        orphaned_count = int(
            self.db.execute(
                select(func.count(NonHumanIdentity.id))
                .outerjoin(User, User.id == NonHumanIdentity.owner_user_id)
                .where(
                    *active_filters,
                    or_(NonHumanIdentity.is_orphaned.is_(True), User.id.is_(None), User.is_active.is_(False), User.status != "active"),
                )
            ).scalar_one()
        )

        by_type_rows = self.db.execute(
            select(NonHumanIdentity.identity_type, func.count(NonHumanIdentity.id)).where(*base_filters).group_by(NonHumanIdentity.identity_type)
        ).all()
        by_status_rows = self.db.execute(
            select(NonHumanIdentity.status, func.count(NonHumanIdentity.id)).where(*base_filters).group_by(NonHumanIdentity.status)
        ).all()
        by_risk_rows = self.db.execute(
            select(NonHumanIdentity.risk_level, func.count(NonHumanIdentity.id)).where(*base_filters).group_by(NonHumanIdentity.risk_level)
        ).all()

        return {
            "total_identities": count_where(*base_filters),
            "active_identities": count_where(*active_filters),
            "inactive_identities": count_where(*base_filters, NonHumanIdentity.is_active.is_(False)),
            "stale_identities": stale_count,
            "unrotated_identities": unrotated_count,
            "orphaned_identities": orphaned_count,
            "high_risk_identities": count_where(*base_filters, NonHumanIdentity.risk_level.in_(["high", "critical"])),
            "by_type": {str(key): int(value) for key, value in by_type_rows},
            "by_status": {str(key): int(value) for key, value in by_status_rows},
            "by_risk_level": {str(key): int(value) for key, value in by_risk_rows},
        }
