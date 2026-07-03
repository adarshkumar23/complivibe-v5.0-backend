import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.dora_ict_register import DORAICTRegister
from app.models.user import User
from app.services.audit_service import AuditService


class DORAService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def _require_user(self, user_id: uuid.UUID) -> None:
        row = self.db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="user_id not found")

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
        self._require_user(created_by)
        self._require_user(data.owner_id)
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
            self._require_user(updates["owner_id"])

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
