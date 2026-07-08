import hashlib
import re
import secrets
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.carbon_accounting_api_key import CarbonAccountingApiKey
from app.models.carbon_emissions_reading import SCOPE3_CATEGORIES, CarbonEmissionsReading
from app.schemas.carbon_accounting import CarbonEmissionsReadingIngest
from app.services.audit_service import AuditService

ALLOWED_UNITS = {"kgCO2e", "tCO2e", "MTCO2e"}
UNIT_TO_TCO2E = {
    "kgCO2e": Decimal("0.001"),
    "tCO2e": Decimal("1"),
    "MTCO2e": Decimal("1000000"),
}

# New ingests may not be tagged with the legacy catch-all bucket -- it exists only so a DB
# CHECK constraint can accept rows written before category attribution was required.
INGESTIBLE_SCOPE3_CATEGORIES = {c for c in SCOPE3_CATEGORIES if c != "unspecified_legacy"}

# An emission factor dataset is considered potentially stale for reporting purposes once it is
# more than 2 annual cycles old (EPA eGRID and DEFRA factors are both republished ~annually).
STALE_FACTOR_VERSION_AGE_YEARS = 2
_YEAR_RE = re.compile(r"(20\d{2})")


class CarbonAccountingService:
    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def hash_api_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def resolve_org_by_api_key(self, raw_key: str) -> uuid.UUID:
        if not raw_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        key_hash = self.hash_api_key(raw_key)
        row = self.db.execute(
            select(CarbonAccountingApiKey.organization_id).where(
                CarbonAccountingApiKey.api_key_hash == key_hash,
                CarbonAccountingApiKey.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return row

    def provision_api_key(self, org_id: uuid.UUID, created_by_user_id: uuid.UUID | None) -> str:
        """Generate (or rotate) this org's carbon-accounting ingest API key.

        The raw key is only ever returned here, at provisioning time -- only its
        SHA-256 hash is persisted, matching the pattern used for other ingest keys
        in this codebase (e.g. AIMonitoringConfig.api_key_hash).
        """
        raw_key = secrets.token_urlsafe(32)
        key_hash = self.hash_api_key(raw_key)
        row = self.db.execute(
            select(CarbonAccountingApiKey).where(CarbonAccountingApiKey.organization_id == org_id)
        ).scalar_one_or_none()
        now = self.utcnow()
        if row is None:
            row = CarbonAccountingApiKey(
                organization_id=org_id,
                api_key_hash=key_hash,
                is_active=True,
                created_by_user_id=created_by_user_id,
            )
            self.db.add(row)
        else:
            row.api_key_hash = key_hash
            row.is_active = True
            row.rotated_at = now
        self.db.flush()
        return raw_key

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
        if payload.scope == "scope3" and payload.scope3_category not in INGESTIBLE_SCOPE3_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "scope3_category must be one of the 15 GHG Protocol Scope 3 categories: "
                    f"{sorted(INGESTIBLE_SCOPE3_CATEGORIES)}"
                ),
            )

    @staticmethod
    def _snapshot(row: CarbonEmissionsReading) -> dict[str, Any]:
        return {
            "scope": row.scope,
            "scope3_category": row.scope3_category,
            "source": row.source,
            "period_start": row.period_start.isoformat(),
            "period_end": row.period_end.isoformat(),
            "value": str(row.value),
            "unit": row.unit,
            "business_unit_id": str(row.business_unit_id) if row.business_unit_id else None,
            "source_record_id": row.source_record_id,
            "emission_factor_source": row.emission_factor_source,
            "emission_factor_version": row.emission_factor_version,
        }

    def ingest_reading(self, org_id: uuid.UUID, payload: CarbonEmissionsReadingIngest) -> CarbonEmissionsReading:
        self._validate_payload(payload)
        self._require_business_unit(org_id, payload.business_unit_id)

        # Idempotency / correction: a source system re-sending the same (source, source_record_id)
        # pair means the underlying activity data was corrected/recalculated upstream (e.g. a
        # utility bill estimate replaced by the final invoice). Update the existing row in place
        # instead of inserting a duplicate that would double-count in the dashboard.
        existing = None
        if payload.source_record_id:
            existing = self.db.execute(
                select(CarbonEmissionsReading).where(
                    CarbonEmissionsReading.organization_id == org_id,
                    CarbonEmissionsReading.source == payload.source,
                    CarbonEmissionsReading.source_record_id == payload.source_record_id,
                )
            ).scalar_one_or_none()

        if existing is not None:
            before = self._snapshot(existing)
            existing.scope = payload.scope
            existing.scope3_category = payload.scope3_category
            existing.period_start = payload.period_start
            existing.period_end = payload.period_end
            existing.value = payload.value
            existing.unit = payload.unit
            existing.business_unit_id = payload.business_unit_id
            existing.emission_factor_source = payload.emission_factor_source
            existing.emission_factor_version = payload.emission_factor_version
            existing.raw_payload = payload.raw_payload or {}
            existing.corrected_at = self.utcnow()
            self.db.flush()
            AuditService(self.db).write_audit_log(
                action="carbon_accounting.reading_corrected",
                entity_type="carbon_emissions_reading",
                entity_id=existing.id,
                organization_id=org_id,
                actor_user_id=None,
                before_json=before,
                after_json=self._snapshot(existing),
                metadata_json={"source": "api_key_ingest"},
            )
            return existing

        row = CarbonEmissionsReading(
            organization_id=org_id,
            scope=payload.scope,
            scope3_category=payload.scope3_category,
            source=payload.source,
            period_start=payload.period_start,
            period_end=payload.period_end,
            value=payload.value,
            unit=payload.unit,
            business_unit_id=payload.business_unit_id,
            source_record_id=payload.source_record_id,
            emission_factor_source=payload.emission_factor_source,
            emission_factor_version=payload.emission_factor_version,
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
        by_scope3_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_period: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        by_bu: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        stale_factors: set[tuple[str, str]] = set()
        # Same (scope, scope3_category, business_unit) bucket, grouped by source: if two
        # different source systems both report overlapping periods for that bucket, the
        # totals above are very likely double-counting the same underlying activity.
        by_bucket_source: dict[tuple, list[CarbonEmissionsReading]] = defaultdict(list)
        current_year = self.utcnow().year
        for row in rows:
            value = self._to_tco2e(row.value, row.unit)
            by_scope[row.scope] += value
            if row.scope == "scope3" and row.scope3_category:
                by_scope3_category[row.scope3_category] += value
            period_key = row.period_start.strftime("%Y-%m")
            by_period[period_key] += value
            by_bu[str(row.business_unit_id) if row.business_unit_id else "unassigned"] += value
            by_bucket_source[(row.scope, row.scope3_category, row.business_unit_id)].append(row)

            if row.emission_factor_version:
                match = _YEAR_RE.search(row.emission_factor_version)
                if match and (current_year - int(match.group(1))) > STALE_FACTOR_VERSION_AGE_YEARS:
                    stale_factors.add((row.emission_factor_source or "unknown_source", row.emission_factor_version))

        overlap_warnings: list[str] = []
        for (scope, scope3_category, business_unit_id), bucket_rows in by_bucket_source.items():
            by_source = defaultdict(list)
            for row in bucket_rows:
                by_source[row.source].append(row)
            if len(by_source) < 2:
                continue
            sources = sorted(by_source)
            for i, source_a in enumerate(sources):
                for source_b in sources[i + 1 :]:
                    overlap = any(
                        a.period_start <= b.period_end and b.period_start <= a.period_end
                        for a in by_source[source_a]
                        for b in by_source[source_b]
                    )
                    if overlap:
                        bucket_label = scope3_category or scope
                        bu_label = f" (business unit {business_unit_id})" if business_unit_id else ""
                        overlap_warnings.append(
                            f"Sources '{source_a}' and '{source_b}' both report overlapping periods for "
                            f"{bucket_label}{bu_label} -- verify this isn't double-counted activity data."
                        )

        insights: list[str] = []
        scope1_scope2_present = bool(by_scope.get("scope1") or by_scope.get("scope2"))
        if scope1_scope2_present and not by_scope.get("scope3"):
            insights.append(
                "Scope 3 emissions have not been reported. Scope 3 typically represents 70-95% of a "
                "company's total footprint (per CDP) and its absence likely means the inventory is materially incomplete."
            )
        elif by_scope.get("scope3"):
            missing_categories = INGESTIBLE_SCOPE3_CATEGORIES - set(by_scope3_category.keys())
            if missing_categories:
                insights.append(
                    f"{len(missing_categories)} of 15 GHG Protocol Scope 3 categories have no reported data: "
                    f"{sorted(missing_categories)[:5]}{'...' if len(missing_categories) > 5 else ''}."
                )
        for source, version in sorted(stale_factors):
            insights.append(
                f"Emission factor '{version}' from '{source}' is more than {STALE_FACTOR_VERSION_AGE_YEARS} "
                "years old and may no longer reflect current grid/fuel intensities -- consider refreshing it."
            )
        insights.extend(sorted(overlap_warnings))

        return {
            "totals_by_scope": {key: str(round(value, 4)) for key, value in sorted(by_scope.items())},
            "totals_by_scope3_category": [
                {"category": key, "value": str(round(value, 4))} for key, value in sorted(by_scope3_category.items())
            ],
            "totals_by_period": [{"period": key, "value": str(round(value, 4))} for key, value in sorted(by_period.items())],
            "totals_by_business_unit": [
                {"business_unit_id": None if key == "unassigned" else key, "value": str(round(value, 4))}
                for key, value in sorted(by_bu.items())
            ],
            "reading_count": len(rows),
            "canonical_unit": "tCO2e",
            "insights": insights,
        }
