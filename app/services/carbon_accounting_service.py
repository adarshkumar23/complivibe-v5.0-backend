import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_observability.services.lineage_service import LineageService
from app.models.business_unit import BusinessUnit
from app.models.carbon_emissions_reading import CarbonEmissionsReading
from app.schemas.carbon_accounting import CarbonEmissionsReadingIngest
from app.services.audit_service import AuditService

ALLOWED_UNITS = {"kgCO2e", "tCO2e", "MTCO2e"}
UNIT_TO_TCO2E = {
    "kgCO2e": Decimal("0.001"),
    "tCO2e": Decimal("1"),
    "MTCO2e": Decimal("1000000"),
}


class CarbonAccountingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        return LineageService(self.db).resolve_org_by_api_key(raw_key)

    def _require_business_unit(self, org_id: uuid.UUID, business_unit_id: uuid.UUID | None) -> None:
        if business_unit_id is None:
            return
        row = self.db.execute(
            select(BusinessUnit.id).where(
                BusinessUnit.organization_id == org_id,
                BusinessUnit.id == business_unit_id,
                BusinessUnit.deleted_at.is_(None),
                BusinessUnit.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")

    @staticmethod
    def _validate_payload(payload: CarbonEmissionsReadingIngest) -> None:
        if payload.period_end < payload.period_start:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="period_end must be on or after period_start")
        if payload.unit not in ALLOWED_UNITS:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported emissions unit")

    @staticmethod
    def _snapshot(row: CarbonEmissionsReading) -> dict[str, Any]:
        return {
            "scope": row.scope,
            "source": row.source,
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "value": str(row.value),
            "unit": row.unit,
            "business_unit_id": str(row.business_unit_id) if row.business_unit_id else None,
            "source_record_id": row.source_record_id,
        }

    def ingest_reading(self, org_id: uuid.UUID, payload: CarbonEmissionsReadingIngest) -> CarbonEmissionsReading:
        self._validate_payload(payload)
        self._require_business_unit(org_id, payload.business_unit_id)
        row = CarbonEmissionsReading(
            organization_id=org_id,
            scope=payload.scope,
            source=payload.source,
            period_start=payload.period_start,
            period_end=payload.period_end,
            value=payload.value,
            unit=payload.unit,
            business_unit_id=payload.business_unit_id,
            source_record_id=payload.source_record_id,
            raw_payload=payload.raw_payload or {},
            ingested_at=self.utcnow(),
        )
        self.db.add(row)
        self.db.flush()
        AuditService(self.db).write_audit_log(
            action="carbon_accounting.reading_ingested",
            entity_type="carbon_emissions_reading",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=None,
            after_json=self._snapshot(row),
            metadata_json={"source": "api_key_ingest"},
        )
        return row

    @staticmethod
    def _to_tco2e(value: Decimal, unit: str) -> Decimal:
        return value * UNIT_TO_TCO2E[unit]

    def dashboard(self, org_id: uuid.UUID, *, start: date | None = None, end: date | None = None) -> dict:
        stmt = select(CarbonEmissionsReading).where(CarbonEmissionsReading.organization_id == org_id)
        if start is not None:
            stmt = stmt.where(CarbonEmissionsReading.period_end >= start)
        if end is not None:
            stmt = stmt.where(CarbonEmissionsReading.period_start <= end)
        rows = self.db.execute(stmt.order_by(CarbonEmissionsReading.period_start.asc())).scalars().all()

        by_scope: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_period: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_bu: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in rows:
            value = self._to_tco2e(row.value, row.unit)
            by_scope[row.scope] += value
            period_key = row.period_start.strftime("%Y-%m")
            by_period[period_key] += value
            by_bu[str(row.business_unit_id) if row.business_unit_id else "unassigned"] += value

        return {
            "totals_by_scope": {key: str(round(value, 4)) for key, value in sorted(by_scope.items())},
            "totals_by_period": [{"period": key, "value": str(round(value, 4))} for key, value in sorted(by_period.items())],
            "totals_by_business_unit": [
                {"business_unit_id": None if key == "unassigned" else key, "value": str(round(value, 4))}
                for key, value in sorted(by_bu.items())
            ],
            "reading_count": len(rows),
            "canonical_unit": "tCO2e",
        }
