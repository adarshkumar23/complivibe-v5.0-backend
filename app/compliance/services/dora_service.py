import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.event_bus import EventBus, EventPayload, EventType
from app.models.dora_ict_register import DORAICTRegister
from app.models.membership import Membership
from app.models.user import User
from app.models.vendor import Vendor
from app.services.audit_service import AuditService

DORA_ASSESSMENT_OVERDUE_DAYS = 365


class DORAService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @classmethod
    def _is_register_gap(cls, row: DORAICTRegister, *, now: datetime) -> tuple[bool, str]:
        """Mirror the two findings already surfaced in get_ict_register_report per-entry.

        A non-critical function is out of scope: DORA Art. 28 concentrates on critical/
        important functions, and flagging every minor provider as a register gap would
        bury the signal a compliance officer actually needs to act on.
        """
        if not row.is_critical_function:
            return False, ""
        if not row.exit_strategy_documented:
            return True, "missing_exit_strategy"
        overdue_cutoff = now - timedelta(days=DORA_ASSESSMENT_OVERDUE_DAYS)
        if row.last_assessed_at is not None and row.last_assessed_at < overdue_cutoff:
            return True, "assessment_overdue"
        return False, ""

    def _sync_risk_register(self, org_id: uuid.UUID, row: DORAICTRegister, *, actor_user_id: uuid.UUID | None) -> None:
        """Detect a DORA Art. 28 register gap (no exit strategy, or assessment lapsed
        past the recurring cadence) on a critical ICT provider and PUBLISH it onto the
        event bus. The downstream Risk register entry, ControlMonitoringAlert, Issue,
        and `dora.ict_entry_risk_linked` audit log are created by
        DORARiskRegisterListener -- see docs/event_bus_design.md (Interconnection
        Phase 1). Behavior is identical to the former inline cascade; only the wiring
        changed from a direct call to publish/subscribe.

        Idempotent per entry (guarded by DORAICTRegister.risk_id): an already-flagged
        entry emits nothing, so repeated writes don't spawn duplicate risks.
        """
        now = self.utcnow()
        is_gap, reason = self._is_register_gap(row, now=now)
        if not is_gap or row.risk_id is not None:
            return

        EventBus.get_instance().emit(
            EventType.DORA_REGISTER_GAP_DETECTED,
            EventPayload(
                org_id=org_id,
                entity_type="dora_ict_register",
                entity_id=row.id,
                event_type=EventType.DORA_REGISTER_GAP_DETECTED,
                previous_value=None,
                new_value=reason,
                triggered_by="user_action" if actor_user_id else "system",
                db=self.db,
                triggered_by_user_id=actor_user_id,
                payload={"reason": reason},
            ),
        )

    def _require_org_user(self, org_id: uuid.UUID, user_id: uuid.UUID, field_name: str) -> None:
        row = self.db.execute(
            select(User.id)
            .join(Membership, Membership.user_id == User.id)
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.status == "active",
                Membership.organization_id == org_id,
                Membership.status == "active",
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field_name} must be an active organization user",
            )

    def _require_org_vendor(self, org_id: uuid.UUID, vendor_id: uuid.UUID) -> None:
        row = self.db.execute(
            select(Vendor.id).where(
                Vendor.id == vendor_id,
                Vendor.organization_id == org_id,
                Vendor.archived_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor not found")

    def _require_entry(self, org_id: uuid.UUID, entry_id: uuid.UUID) -> DORAICTRegister:
        row = self.db.execute(
            select(DORAICTRegister).where(
                DORAICTRegister.id == entry_id,
                DORAICTRegister.organization_id == org_id,
                DORAICTRegister.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DORA ICT register entry not found")
        return row

    def create_ict_register_entry(self, org_id: uuid.UUID, data, created_by: uuid.UUID) -> DORAICTRegister:
        self._require_org_user(org_id, created_by, "created_by")
        self._require_org_user(org_id, data.owner_id, "owner_id")
        if data.vendor_id is not None:
            self._require_org_vendor(org_id, data.vendor_id)
        row = DORAICTRegister(
            organization_id=org_id,
            vendor_id=data.vendor_id,
            counterparty_name=data.counterparty_name,
            service_description=data.service_description,
            is_critical_function=data.is_critical_function,
            sub_outsourcing_used=data.sub_outsourcing_used,
            data_location=data.data_location,
            data_location_countries=list(data.data_location_countries or []),
            contract_start_date=data.contract_start_date,
            contract_end_date=data.contract_end_date,
            exit_strategy_documented=data.exit_strategy_documented,
            exit_strategy_notes=data.exit_strategy_notes,
            last_assessed_at=data.last_assessed_at,
            assessment_frequency=data.assessment_frequency,
            dora_article=data.dora_article,
            status=data.status,
            owner_id=data.owner_id,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dora.ict_entry_created",
            entity_type="dora_ict_register",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=created_by,
            after_json={
                "counterparty_name": row.counterparty_name,
                "is_critical_function": row.is_critical_function,
                "status": row.status,
            },
            metadata_json={"source": "api"},
        )
        self._sync_risk_register(org_id, row, actor_user_id=created_by)
        return row

    def get_ict_entry(self, org_id: uuid.UUID, entry_id: uuid.UUID) -> DORAICTRegister:
        return self._require_entry(org_id, entry_id)

    def list_ict_register(self, org_id: uuid.UUID, is_critical: bool | None = None, status_value: str | None = None) -> list[DORAICTRegister]:
        stmt = select(DORAICTRegister).where(
            DORAICTRegister.organization_id == org_id,
            DORAICTRegister.deleted_at.is_(None),
        )
        if is_critical is not None:
            stmt = stmt.where(DORAICTRegister.is_critical_function.is_(is_critical))
        if status_value is not None:
            stmt = stmt.where(DORAICTRegister.status == status_value)
        return self.db.execute(stmt.order_by(DORAICTRegister.created_at.desc())).scalars().all()

    def update_ict_entry(self, org_id: uuid.UUID, entry_id: uuid.UUID, data, user_id: uuid.UUID) -> DORAICTRegister:
        row = self._require_entry(org_id, entry_id)
        updates = data.model_dump(exclude_unset=True)
        if "owner_id" in updates and updates["owner_id"] is not None:
            self._require_org_user(org_id, updates["owner_id"], "owner_id")
        if "vendor_id" in updates and updates["vendor_id"] is not None:
            self._require_org_vendor(org_id, updates["vendor_id"])

        before = {
            "counterparty_name": row.counterparty_name,
            "is_critical_function": row.is_critical_function,
            "status": row.status,
            "exit_strategy_documented": row.exit_strategy_documented,
        }
        for key, value in updates.items():
            setattr(row, key, value)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dora.ict_entry_updated",
            entity_type="dora_ict_register",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            before_json=before,
            after_json={
                "counterparty_name": row.counterparty_name,
                "is_critical_function": row.is_critical_function,
                "status": row.status,
                "exit_strategy_documented": row.exit_strategy_documented,
            },
            metadata_json={"source": "api"},
        )
        self._sync_risk_register(org_id, row, actor_user_id=user_id)
        return row

    def soft_delete_ict_entry(self, org_id: uuid.UUID, entry_id: uuid.UUID, user_id: uuid.UUID) -> DORAICTRegister:
        row = self._require_entry(org_id, entry_id)
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="dora.ict_entry_updated",
            entity_type="dora_ict_register",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=user_id,
            after_json={"deleted_at": row.deleted_at.isoformat()},
            metadata_json={"source": "api", "operation": "soft_delete"},
        )
        return row

    def get_ict_register_report(self, org_id: uuid.UUID) -> dict:
        rows = self.db.execute(
            select(DORAICTRegister).where(
                DORAICTRegister.organization_id == org_id,
                DORAICTRegister.deleted_at.is_(None),
            )
        ).scalars().all()

        now = self.utcnow()
        overdue_cutoff = now - timedelta(days=365)

        by_data_location = Counter()
        for row in rows:
            countries = [str(item).upper() for item in list(row.data_location_countries or []) if str(item).strip()]
            if countries:
                for country in countries:
                    by_data_location[country] += 1
                continue
            if row.data_location:
                by_data_location[row.data_location] += 1

        return {
            "total_providers": len(rows),
            "critical_function_count": sum(1 for row in rows if row.is_critical_function),
            "missing_exit_strategy": sum(
                1
                for row in rows
                if row.is_critical_function and not row.exit_strategy_documented
            ),
            "assessment_overdue": sum(
                1
                for row in rows
                if row.last_assessed_at is not None and row.last_assessed_at < overdue_cutoff
            ),
            "by_data_location": dict(by_data_location),
            "sub_outsourcing_count": sum(1 for row in rows if row.sub_outsourcing_used),
        }
