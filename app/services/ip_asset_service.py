import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_system import AISystem
from app.models.ip_asset import IPAsset
from app.models.ip_asset_settings import IPAssetSettings
from app.services.audit_service import AuditService

# Lifecycle states that mean an AI system can no longer meaningfully rely on new
# or renewed IP licensing coverage.
_AI_SYSTEM_TERMINAL_LIFECYCLE_STATUSES = {"retired", "archived"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IPAssetService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Core asset CRUD
    # ------------------------------------------------------------------

    def _require_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> IPAsset:
        row = self.db.execute(
            select(IPAsset).where(
                IPAsset.id == asset_id,
                IPAsset.organization_id == org_id,
                IPAsset.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP asset not found")
        return row

    def _validate_ai_system_link(self, org_id: uuid.UUID, ai_system_id: uuid.UUID | None) -> None:
        if ai_system_id is None:
            return
        row = self.db.execute(
            select(AISystem).where(AISystem.id == ai_system_id, AISystem.organization_id == org_id)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linked AI system not found")

    def create_asset(self, org_id: uuid.UUID, payload: dict, actor_user_id: uuid.UUID | None) -> IPAsset:
        self._validate_ai_system_link(org_id, payload.get("linked_ai_system_id"))

        row = IPAsset(organization_id=org_id, created_by=actor_user_id, **payload)
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ip_asset.created",
            entity_type="ip_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            after_json=self._snapshot(row),
        )
        return row

    def get_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID) -> IPAsset:
        return self._require_asset(org_id, asset_id)

    def list_assets(
        self,
        org_id: uuid.UUID,
        *,
        asset_type: str | None = None,
        status_filter: str | None = None,
    ) -> list[IPAsset]:
        query = select(IPAsset).where(IPAsset.organization_id == org_id, IPAsset.deleted_at.is_(None))
        if asset_type is not None:
            query = query.where(IPAsset.asset_type == asset_type)
        if status_filter is not None:
            query = query.where(IPAsset.status == status_filter)
        query = query.order_by(IPAsset.created_at.desc())
        return list(self.db.execute(query).scalars().all())

    def update_asset(
        self,
        org_id: uuid.UUID,
        asset_id: uuid.UUID,
        payload: dict,
        actor_user_id: uuid.UUID | None,
    ) -> IPAsset:
        row = self._require_asset(org_id, asset_id)
        before = self._snapshot(row)

        if "linked_ai_system_id" in payload:
            self._validate_ai_system_link(org_id, payload["linked_ai_system_id"])

        for field, value in payload.items():
            setattr(row, field, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ip_asset.updated",
            entity_type="ip_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._snapshot(row),
        )
        return row

    def delete_asset(self, org_id: uuid.UUID, asset_id: uuid.UUID, actor_user_id: uuid.UUID | None) -> IPAsset:
        row = self._require_asset(org_id, asset_id)
        before = self._snapshot(row)
        row.deleted_at = _utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ip_asset.deleted",
            entity_type="ip_asset",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json=self._snapshot(row),
        )
        return row

    @staticmethod
    def _snapshot(row: IPAsset) -> dict:
        return {
            "name": row.name,
            "asset_type": row.asset_type,
            "licensor": row.licensor,
            "licensee": row.licensee,
            "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
            "linked_ai_system_id": str(row.linked_ai_system_id) if row.linked_ai_system_id else None,
            "status": row.status,
            "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
        }

    # ------------------------------------------------------------------
    # Settings (org-configurable "expiring soon" window)
    # ------------------------------------------------------------------

    def get_or_create_settings(self, org_id: uuid.UUID) -> IPAssetSettings:
        row = self.db.execute(
            select(IPAssetSettings).where(IPAssetSettings.organization_id == org_id)
        ).scalar_one_or_none()
        if row is not None:
            return row

        row = IPAssetSettings(organization_id=org_id, expiring_soon_window_days=90)
        self.db.add(row)
        self.db.flush()
        return row

    def update_settings(
        self, org_id: uuid.UUID, window_days: int, actor_user_id: uuid.UUID | None
    ) -> IPAssetSettings:
        row = self.get_or_create_settings(org_id)
        before = {"expiring_soon_window_days": row.expiring_soon_window_days}
        row.expiring_soon_window_days = window_days
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="ip_asset_settings.updated",
            entity_type="ip_asset_settings",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"expiring_soon_window_days": row.expiring_soon_window_days},
        )
        return row

    # ------------------------------------------------------------------
    # Expiring-soon intelligence
    # ------------------------------------------------------------------

    def compute_expiry_fields(self, row: IPAsset, now: datetime | None = None) -> tuple[bool, bool, int | None]:
        """Return (is_expiring_soon, is_expired, days_until_expiry) for a single asset.

        This mirrors the canonical logic used by ``expiring_soon`` so that
        list/get responses stay consistent with the dedicated endpoint, using
        the org's configured window.
        """
        now = now or _utcnow()
        if row.expiry_date is None:
            return False, False, None

        expiry = row.expiry_date
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        delta_days = (expiry - now).days
        is_expired = expiry < now
        settings = self.get_or_create_settings(row.organization_id)
        window_days = settings.expiring_soon_window_days
        is_expiring_soon = row.status != "terminated" and 0 <= delta_days <= window_days
        # An already-expired active asset should still surface as needing attention.
        if is_expired and row.status != "terminated":
            is_expiring_soon = True
        return is_expiring_soon, is_expired, delta_days

    def _ai_system_still_active(self, ai_system: AISystem) -> bool:
        if ai_system.archived_at is not None:
            return False
        return ai_system.lifecycle_status not in _AI_SYSTEM_TERMINAL_LIFECYCLE_STATUSES

    def expiring_soon(self, org_id: uuid.UUID) -> list[dict]:
        settings = self.get_or_create_settings(org_id)
        window_days = settings.expiring_soon_window_days
        now = _utcnow()

        rows = self.db.execute(
            select(IPAsset).where(
                IPAsset.organization_id == org_id,
                IPAsset.deleted_at.is_(None),
                IPAsset.status != "terminated",
                IPAsset.expiry_date.is_not(None),
            )
        ).scalars().all()

        # Pre-fetch linked AI systems in one query to avoid N+1 lookups.
        linked_ids = {row.linked_ai_system_id for row in rows if row.linked_ai_system_id is not None}
        ai_systems_by_id: dict[uuid.UUID, AISystem] = {}
        if linked_ids:
            ai_system_rows = self.db.execute(
                select(AISystem).where(AISystem.id.in_(linked_ids), AISystem.organization_id == org_id)
            ).scalars().all()
            ai_systems_by_id = {ai.id: ai for ai in ai_system_rows}

        results: list[dict] = []
        for row in rows:
            expiry = row.expiry_date
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            days_until_expiry = (expiry - now).days

            if days_until_expiry < 0 or days_until_expiry > window_days:
                continue

            at_risk_ai_system = None
            has_active_ai_system_link = False
            if row.linked_ai_system_id is not None:
                ai_system = ai_systems_by_id.get(row.linked_ai_system_id)
                if ai_system is not None:
                    still_active = self._ai_system_still_active(ai_system)
                    has_active_ai_system_link = still_active
                    at_risk_ai_system = {
                        "id": ai_system.id,
                        "name": ai_system.name,
                        "lifecycle_status": ai_system.lifecycle_status,
                        "still_active": still_active,
                    }

            results.append(
                {
                    "asset": row,
                    "days_until_expiry": days_until_expiry,
                    "has_active_ai_system_link": has_active_ai_system_link,
                    "at_risk_ai_system": at_risk_ai_system,
                }
            )

        # Real urgency ranking: assets with an at-risk *active* AI system
        # linkage rank first, then soonest expiry.
        results.sort(key=lambda item: (not item["has_active_ai_system_link"], item["days_until_expiry"]))
        return results
