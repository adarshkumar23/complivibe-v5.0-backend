"""Geopolitical Risk Monitoring (T4-15).

Real data source: GDELT DOC 2.0 API (https://api.gdeltproject.org/api/v2/doc/doc),
verified reachable from this environment at build time. This module ships its
own tiny httpx-based client (``GdeltHTTPClient``) rather than importing
``app.satellites.tprm_intelligence.http_client.SatelliteHTTPClient`` -- both
options were allowed by the task; a standalone client was chosen so this
feature has zero coupling to the tprm_intelligence satellite's settings
object (``TPRMIntelligenceSettings``), which is owned by a different
workstream and pulls in API keys/env config this feature does not need.

Second public data source (sanctions / conflict-zone dataset): NOT added.
``app/satellites/tprm_intelligence/sanctions_screening.py`` was reviewed --
its only network-reachable path is a "Watchman"-style OFAC search against
``WATCHMAN_BASE_URL`` (default ``http://localhost:8084``), i.e. a *local*
service that is not itself a public API this feature can call from a clean
room; its other path is a bulk OpenSanctions dataset file download
(``entities.ftm.json``) meant for a periodic offline refresh job, not a
live per-request signal source. Neither is a genuinely available live public
API for this feature to call at ingest time, so a second source was
deliberately skipped rather than faked.

Severity/category classification method: **keyword-based heuristic**, not
ML/NLP-based. GDELT's DOC ArtList mode does not return per-article tone/GKG
scores, so severity is derived from a hand-curated keyword scan of each
article's title. This is explicitly a heuristic, not a machine-learned
classifier -- documented here so no one mistakes it for tone-based scoring.

Failure handling: if the GDELT fetch itself fails (network unreachable,
timeout, non-2xx, malformed JSON), **no** ``GeopoliticalRiskSignal`` row is
created for that failed fetch -- there is no real data to persist, and
forcing a fabricated row into the enum-constrained ``category``/``severity``
columns would misrepresent it as an assessed (e.g. "low") risk. Instead:
  - an audit log entry (``geopolitical_risk.ingest_failed``) is always
    written so failures are never silent/invisible, and
  - ``ingest_from_gdelt`` returns a structured result with
    ``status="error"`` and a populated ``source_error`` message, which the
    router surfaces directly in the API response (never collapsed into an
    empty/"no risk" looking payload).
``GeopoliticalRiskSignal.source_error`` is reserved for the narrower case of
a successful connection where a specific record could not be fully parsed
(still real data, just partially degraded) -- it is not used for whole-fetch
failures.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_unit import BusinessUnit
from app.models.geopolitical_risk_signal import GeopoliticalRiskSignal
from app.models.vendor import Vendor
from app.models.vendor_geopolitical_exposure import VendorGeopoliticalExposure
from app.schemas.geopolitical_risk import VendorGeopoliticalExposureCreate
from app.services.audit_service import AuditService
from app.services.vendor_risk_service import VendorRiskService

GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_HTTP_TIMEOUT_SECONDS = 10.0

SEVERITY_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# Keyword heuristic tables. Order matters: first category/severity whose
# keyword set matches the (lowercased) headline wins.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "conflict",
        (
            "war",
            "invasion",
            "attack",
            "military",
            "conflict",
            "battle",
            "insurgency",
            "airstrike",
            "air strike",
            "missile",
            "troops",
            "armed",
            "bombing",
            "clash",
        ),
    ),
    (
        "sanctions",
        ("sanction", "embargo", "export control", "blacklist", "asset freeze"),
    ),
    (
        "political_instability",
        (
            "coup",
            "unrest",
            "protest",
            "uprising",
            "government collapse",
            "resign",
            "impeach",
            "election crisis",
            "riot",
        ),
    ),
    (
        "trade_restriction",
        ("tariff", "trade ban", "export ban", "import restriction", "trade war", "trade dispute"),
    ),
    (
        "regulatory_change",
        ("regulation", "legislation", "law passed", "policy change", "compliance requirement", "new law"),
    ),
]

_SEVERITY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "critical",
        ("war", "invasion", "coup", "massacre", "genocide", "nuclear", "killed dozens", "mass casualties"),
    ),
    (
        "high",
        (
            "attack",
            "conflict",
            "sanction",
            "military",
            "airstrike",
            "air strike",
            "killed",
            "bombing",
            "embargo",
            "missile",
        ),
    ),
    (
        "medium",
        ("protest", "unrest", "tension", "dispute", "crisis", "riot", "coup", "tariff"),
    ),
]


def classify_headline(headline: str | None) -> tuple[str, str]:
    """Keyword heuristic -> (category, severity). Documented as a heuristic,
    not an ML classifier -- see module docstring."""
    text = (headline or "").lower()
    category = "other"
    for candidate_category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            category = candidate_category
            break

    severity = "low"
    for candidate_severity, keywords in _SEVERITY_KEYWORDS:
        if any(keyword in text for keyword in keywords):
            severity = candidate_severity
            break

    return category, severity


def _parse_gdelt_seendate(value: Any) -> datetime:
    if isinstance(value, str) and value:
        cleaned = value.strip()
        # GDELT format: 20260626T211500Z
        match = re.match(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z?$", cleaned)
        if match:
            year, month, day, hour, minute, second = (int(part) for part in match.groups())
            try:
                return datetime(year, month, day, hour, minute, second, tzinfo=UTC)
            except ValueError:
                pass
    return datetime.now(UTC)


class GdeltHTTPClient:
    """The only place this feature performs third-party HTTP calls."""

    def __init__(self, timeout_seconds: float = GDELT_HTTP_TIMEOUT_SECONDS, base_url: str = GDELT_DOC_API_URL) -> None:
        self.timeout_seconds = timeout_seconds
        self.base_url = base_url

    def search_articles(self, region_query: str, *, max_records: int = 20) -> list[dict[str, Any]]:
        params = {
            "query": region_query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": max_records,
            "sort": "hybridrel",
        }
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        articles = payload.get("articles") if isinstance(payload, dict) else None
        return [item for item in (articles or []) if isinstance(item, dict)]


class GeopoliticalRiskService:
    def __init__(self, db: Session, *, http_client: GdeltHTTPClient | None = None) -> None:
        self.db = db
        self.http = http_client or GdeltHTTPClient()

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(UTC)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------
    def ingest_from_gdelt(
        self,
        org_id: uuid.UUID,
        region_query: str,
        actor_id: uuid.UUID | None,
        *,
        max_records: int = 20,
    ) -> dict[str, Any]:
        try:
            articles = self.http.search_articles(region_query, max_records=max_records)
        except Exception as exc:  # network failure, timeout, non-2xx, bad JSON, etc.
            error_message = f"GDELT fetch failed for query {region_query!r}: {exc}"
            AuditService(self.db).write_audit_log(
                action="geopolitical_risk.ingest_failed",
                entity_type="geopolitical_risk_signal",
                organization_id=org_id,
                actor_user_id=actor_id,
                metadata_json={"source": "gdelt", "region_query": region_query, "source_error": error_message},
            )
            self.db.commit()
            return {
                "status": "error",
                "source": "gdelt",
                "region_query": region_query,
                "signals_created": 0,
                "source_error": error_message,
                "signals": [],
            }

        created_rows: list[GeopoliticalRiskSignal] = []
        for article in articles:
            headline = article.get("title")
            category, severity = classify_headline(headline)
            detected_at = _parse_gdelt_seendate(article.get("seendate"))
            row = GeopoliticalRiskSignal(
                organization_id=org_id,
                region=region_query,
                category=category,
                severity=severity,
                source="gdelt",
                source_url=article.get("url"),
                headline=headline,
                detected_at=detected_at,
                raw_payload=article,
                created_by=actor_id,
            )
            self.db.add(row)
            created_rows.append(row)

        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="geopolitical_risk.ingested",
            entity_type="geopolitical_risk_signal",
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={
                "region_query": region_query,
                "source": "gdelt",
                "signals_created": len(created_rows),
            },
            metadata_json={"source": "gdelt", "region_query": region_query},
        )
        self.db.commit()
        for row in created_rows:
            self.db.refresh(row)

        return {
            "status": "ok",
            "source": "gdelt",
            "region_query": region_query,
            "signals_created": len(created_rows),
            "source_error": None,
            "signals": created_rows,
        }

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------
    def list_signals(
        self,
        org_id: uuid.UUID,
        *,
        region: str | None = None,
        category: str | None = None,
        severity: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[GeopoliticalRiskSignal]:
        stmt = select(GeopoliticalRiskSignal).where(
            GeopoliticalRiskSignal.organization_id == org_id,
            GeopoliticalRiskSignal.deleted_at.is_(None),
        )
        if region is not None:
            stmt = stmt.where(GeopoliticalRiskSignal.region == region)
        if category is not None:
            stmt = stmt.where(GeopoliticalRiskSignal.category == category)
        if severity is not None:
            stmt = stmt.where(GeopoliticalRiskSignal.severity == severity)
        stmt = stmt.order_by(GeopoliticalRiskSignal.detected_at.desc()).offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    # ------------------------------------------------------------------
    # Vendor geopolitical exposures (simple CRUD)
    # ------------------------------------------------------------------
    def create_exposure(
        self, org_id: uuid.UUID, data: VendorGeopoliticalExposureCreate, actor_id: uuid.UUID | None
    ) -> VendorGeopoliticalExposure:
        # Validate the vendor belongs to this org (reuses VendorRiskService's
        # existing read-only lookup rather than duplicating the query).
        VendorRiskService(self.db).require_vendor_in_org(org_id, data.vendor_id)

        row = VendorGeopoliticalExposure(
            organization_id=org_id,
            vendor_id=data.vendor_id,
            region=data.region,
            is_primary=data.is_primary,
            notes=data.notes,
            created_by=actor_id,
        )
        self.db.add(row)
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="geopolitical_risk.vendor_exposure_created",
            entity_type="vendor_geopolitical_exposure",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            after_json={"vendor_id": str(row.vendor_id), "region": row.region, "is_primary": row.is_primary},
            metadata_json={"source": "api"},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_exposures(
        self, org_id: uuid.UUID, *, vendor_id: uuid.UUID | None = None, region: str | None = None
    ) -> list[VendorGeopoliticalExposure]:
        stmt = select(VendorGeopoliticalExposure).where(
            VendorGeopoliticalExposure.organization_id == org_id,
            VendorGeopoliticalExposure.deleted_at.is_(None),
        )
        if vendor_id is not None:
            stmt = stmt.where(VendorGeopoliticalExposure.vendor_id == vendor_id)
        if region is not None:
            stmt = stmt.where(VendorGeopoliticalExposure.region == region)
        stmt = stmt.order_by(VendorGeopoliticalExposure.created_at.desc())
        return self.db.execute(stmt).scalars().all()

    def get_exposure(self, org_id: uuid.UUID, exposure_id: uuid.UUID) -> VendorGeopoliticalExposure:
        row = self.db.execute(
            select(VendorGeopoliticalExposure).where(
                VendorGeopoliticalExposure.id == exposure_id,
                VendorGeopoliticalExposure.organization_id == org_id,
                VendorGeopoliticalExposure.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vendor geopolitical exposure not found")
        return row

    def delete_exposure(self, org_id: uuid.UUID, exposure_id: uuid.UUID, actor_id: uuid.UUID | None) -> None:
        row = self.get_exposure(org_id, exposure_id)
        row.deleted_at = self.utcnow()
        self.db.flush()

        AuditService(self.db).write_audit_log(
            action="geopolitical_risk.vendor_exposure_deleted",
            entity_type="vendor_geopolitical_exposure",
            entity_id=row.id,
            organization_id=org_id,
            actor_user_id=actor_id,
            before_json={"vendor_id": str(row.vendor_id), "region": row.region},
            metadata_json={"source": "api"},
        )
        self.db.commit()

    # ------------------------------------------------------------------
    # Intelligent cross-referenced summary
    # ------------------------------------------------------------------
    def get_summary(
        self,
        org_id: uuid.UUID,
        *,
        business_unit_id: uuid.UUID | None = None,
        vendor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        if vendor_id is not None:
            # 404s if the vendor doesn't belong to this org.
            VendorRiskService(self.db).require_vendor_in_org(org_id, vendor_id)

        if business_unit_id is not None:
            bu = self.db.execute(
                select(BusinessUnit).where(
                    BusinessUnit.id == business_unit_id,
                    BusinessUnit.organization_id == org_id,
                )
            ).scalar_one_or_none()
            if bu is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business unit not found")

        # 1. Which regions currently have any (non-deleted) risk signal, and
        #    what's the count/max severity of signals per region.
        signal_rows = self.db.execute(
            select(GeopoliticalRiskSignal).where(
                GeopoliticalRiskSignal.organization_id == org_id,
                GeopoliticalRiskSignal.deleted_at.is_(None),
            )
        ).scalars().all()

        region_stats: dict[str, dict[str, Any]] = {}
        for signal in signal_rows:
            stats = region_stats.setdefault(signal.region, {"count": 0, "max_severity": "low"})
            stats["count"] += 1
            if SEVERITY_ORDER.get(signal.severity, 0) > SEVERITY_ORDER.get(stats["max_severity"], 0):
                stats["max_severity"] = signal.severity

        # 2. This org's vendors (optionally filtered) and their declared
        #    region exposures.
        vendor_stmt = select(Vendor).where(Vendor.organization_id == org_id)
        if vendor_id is not None:
            vendor_stmt = vendor_stmt.where(Vendor.id == vendor_id)
        if business_unit_id is not None:
            vendor_stmt = vendor_stmt.where(Vendor.business_unit_id == business_unit_id)
        vendors = self.db.execute(vendor_stmt).scalars().all()

        exposure_stmt = select(VendorGeopoliticalExposure).where(
            VendorGeopoliticalExposure.organization_id == org_id,
            VendorGeopoliticalExposure.deleted_at.is_(None),
        )
        if vendor_id is not None:
            exposure_stmt = exposure_stmt.where(VendorGeopoliticalExposure.vendor_id == vendor_id)
        exposures = self.db.execute(exposure_stmt).scalars().all()

        vendor_ids_in_scope = {vendor.id for vendor in vendors}
        vendor_by_id = {vendor.id: vendor for vendor in vendors}

        exposures_by_vendor: dict[uuid.UUID, list[VendorGeopoliticalExposure]] = {}
        for exposure in exposures:
            if exposure.vendor_id not in vendor_ids_in_scope:
                continue
            exposures_by_vendor.setdefault(exposure.vendor_id, []).append(exposure)

        exposed_vendors: list[dict[str, Any]] = []
        highest_severity_observed: str | None = None
        for vid, vendor_exposures in exposures_by_vendor.items():
            regions_at_risk = []
            overall_max_severity = "low"
            total_signal_count = 0
            for exposure in vendor_exposures:
                stats = region_stats.get(exposure.region)
                if stats is None:
                    continue
                regions_at_risk.append(
                    {
                        "region": exposure.region,
                        "signal_count": stats["count"],
                        "max_severity": stats["max_severity"],
                    }
                )
                total_signal_count += stats["count"]
                if SEVERITY_ORDER.get(stats["max_severity"], 0) > SEVERITY_ORDER.get(overall_max_severity, 0):
                    overall_max_severity = stats["max_severity"]

            if not regions_at_risk:
                continue  # this vendor's regions currently show no risk signals

            vendor = vendor_by_id[vid]
            exposed_vendors.append(
                {
                    "vendor_id": vendor.id,
                    "vendor_name": vendor.name,
                    "business_unit_id": vendor.business_unit_id,
                    "exposed_regions": regions_at_risk,
                    "overall_max_severity": overall_max_severity,
                    "total_signal_count": total_signal_count,
                }
            )
            if highest_severity_observed is None or SEVERITY_ORDER.get(overall_max_severity, 0) > SEVERITY_ORDER.get(
                highest_severity_observed, 0
            ):
                highest_severity_observed = overall_max_severity

        exposed_vendors.sort(key=lambda item: SEVERITY_ORDER.get(item["overall_max_severity"], 0), reverse=True)

        return {
            "organization_id": org_id,
            "regions_with_signals": sorted(region_stats.keys()),
            "exposed_vendors": exposed_vendors,
            "vendor_count_exposed": len(exposed_vendors),
            "highest_severity_observed": highest_severity_observed,
        }
