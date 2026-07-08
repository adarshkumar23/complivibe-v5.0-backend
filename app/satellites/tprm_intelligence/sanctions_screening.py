from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.organization import Organization
from app.models.sanctions_entity import SanctionsEntity
from app.models.sanctions_screen_result import SanctionsScreenResult
from app.models.vendor import Vendor
from app.services.audit_service import AuditService

# DATASET SIZE FIX: this used to default to the OpenSanctions "default" dataset
# (https://data.opensanctions.org/datasets/latest/default/entities.ftm.json), which
# aggregates *every* sanctions/watchlist source OpenSanctions tracks -- as of writing that
# file is ~2.7GB. download_dataset()'s urllib request has a 120s timeout, which a file that
# size cannot reliably complete within (even on a fast connection, let alone constrained
# production egress), so the download would fail/time out on every scheduled run, the local
# `sanctions_entities` table would stay permanently empty, and screen_vendor() would raise
# SanctionsDatasetUnavailable (-> HTTP 503) for every vendor, every attempt -- exactly the
# reported bug. This platform only needs actual US sanctions data (Watchman itself only ever
# indexes OFAC/BIS/State lists), so default to the two purpose-built, reasonably-sized
# OpenSanctions datasets that directly correspond to "OFAC SDN" + "OFAC consolidated
# non-SDN" (~52MB and ~1.5MB respectively as of writing) instead of the 2.7GB firehose.
# Both are downloaded and merged into `sanctions_entities` so a positive match against
# either list surfaces. Override with OPEN_SANCTIONS_DATASET_URLS (comma-separated) or the
# legacy singular OPEN_SANCTIONS_DATASET_URL (still honored, e.g. to point at a self-hosted
# mirror or a different OpenSanctions dataset) if a deployment needs different sourcing.
OPEN_SANCTIONS_DEFAULT_DATASET_URLS: tuple[str, ...] = (
    "https://data.opensanctions.org/datasets/latest/us_ofac_sdn/entities.ftm.json",
    "https://data.opensanctions.org/datasets/latest/us_ofac_cons/entities.ftm.json",
)
# Kept for backwards compatibility with any code/tests referencing the old singular
# constant; points at the OFAC SDN list specifically (the primary/most critical of the two).
OPEN_SANCTIONS_DEFAULT_URL = OPEN_SANCTIONS_DEFAULT_DATASET_URLS[0]
DEFAULT_DATASET_DIR = "data/opensanctions"
DEFAULT_DATASET_PATH = "data/opensanctions/entities.ftm.json"
DEFAULT_WATCHMAN_BASE_URL = "http://localhost:8084"
DEFAULT_THRESHOLD = 0.85
SANCTIONS_ESCALATED_RISK_TIER = "critical"
# The daily rescreen sweep (see run_periodic_vendor_sanctions_rescreen_sweep) means any
# active vendor should have a result no older than ~1 day under normal operation. A
# result older than a week most likely means the sweep is failing for this vendor (a
# persistent Watchman/network error, or the vendor was archived and un-archived) rather
# than that nothing changed - so a human should not treat an old "clean" result as
# equivalent to a fresh one.
SANCTIONS_RESULT_STALE_AFTER_DAYS = 7
# Matches that fall just short of the auto-escalation threshold are exactly the ones a
# looser fuzzy-name variant, transliteration, or minor OFAC list update could tip over.
# Surfacing them (without auto-escalating) turns a hard threshold cliff into a reviewable
# "near miss" instead of a silent false negative.
NEAR_MISS_MARGIN = 0.10


class SanctionsDatasetUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class WatchmanSearchResult:
    available: bool
    matches: list[dict[str, Any]]
    error: str | None = None


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _score_names(left: str, right: str) -> float:
    left_norm = _normalize_name(left)
    right_norm = _normalize_name(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    ratio = SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
        ratio = max(ratio, overlap)
    return round(float(ratio), 4)


def _meaningful_tokens(name: str) -> list[str]:
    stop_words = {"inc", "llc", "ltd", "limited", "corp", "corporation", "company", "co", "ag", "sa", "plc", "gmbh"}
    tokens = [token for token in _normalize_name(name).split() if len(token) >= 3 and token not in stop_words]
    return tokens[:5]


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_last_seen(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _country_values(properties: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("country", "countries", "jurisdiction", "nationality"):
        for item in _as_list(properties.get(key)):
            if item and str(item) not in values:
                values.append(str(item))
    return values


class SanctionsScreeningService:
    def __init__(
        self,
        db: Session,
        *,
        watchman_base_url: str | None = None,
        http_timeout_seconds: float = 5.0,
    ) -> None:
        self.db = db
        self.watchman_base_url = (watchman_base_url or os.getenv("WATCHMAN_BASE_URL") or DEFAULT_WATCHMAN_BASE_URL).rstrip("/")
        self.http_timeout_seconds = http_timeout_seconds

    def screen_vendor(self, organization: Organization, vendor: Vendor) -> SanctionsScreenResult:
        threshold = float(organization.sanctions_match_threshold or DEFAULT_THRESHOLD)
        watchman_result = self._watchman_search(vendor.name)
        matches = watchman_result.matches
        source = "watchman"
        if not watchman_result.available:
            local_count = int(self.db.execute(select(func.count(SanctionsEntity.id))).scalar_one())
            if local_count == 0:
                raise SanctionsDatasetUnavailable("Sanctions screening dataset is not loaded and Watchman is unavailable")
            matches = self._local_search(vendor.name, limit=10)
            source = "local_opensanctions"

        normalized_matches = [self._normalize_match(match, vendor.name) for match in matches]
        normalized_matches = sorted(normalized_matches, key=lambda item: item["score"], reverse=True)[:10]
        top_score = float(normalized_matches[0]["score"]) if normalized_matches else 0.0
        match_found = bool(normalized_matches and top_score >= threshold)
        # A "clean" result that only narrowly missed the threshold is materially
        # different from one with no candidates at all - flag it so a reviewer can
        # decide whether the near-miss is a real risk without waiting for it to
        # eventually cross the line on its own.
        near_miss = bool(
            not match_found and normalized_matches and top_score >= max(0.0, threshold - NEAR_MISS_MARGIN)
        )
        row = SanctionsScreenResult(
            organization_id=organization.id,
            vendor_id=vendor.id,
            entity_type="vendor",
            entity_id=str(vendor.id),
            list_name="opensanctions_default",
            # Set explicitly (rather than relying on the column's server_default=func.now())
            # so ordering by screened_at in latest_result() has microsecond resolution instead
            # of SQLite's second-level CURRENT_TIMESTAMP granularity, which made "latest" ties
            # break on random UUID ordering and could surface a stale (superseded) result.
            screened_at=datetime.now(timezone.utc),
            match_found=match_found,
            match_details={
                "query_name": vendor.name,
                "threshold": threshold,
                "source": source,
                "watchman": {
                    "base_url": self.watchman_base_url,
                    "available": watchman_result.available,
                    "error": watchman_result.error,
                },
                "top_score": top_score,
                "near_miss": near_miss,
                "near_miss_margin": NEAR_MISS_MARGIN,
                "matches": normalized_matches,
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest_result(self, organization_id, vendor_id) -> SanctionsScreenResult | None:
        # A vendor accumulates one row per screen (onboarding + every periodic rescreen), so
        # this must be limited to the single most recent row rather than assuming at most one
        # result exists overall (scalar_one_or_none() raises MultipleResultsFound otherwise).
        return self.db.execute(
            select(SanctionsScreenResult)
            .where(
                SanctionsScreenResult.organization_id == organization_id,
                SanctionsScreenResult.vendor_id == vendor_id,
                SanctionsScreenResult.entity_type == "vendor",
            )
            .order_by(SanctionsScreenResult.screened_at.desc(), SanctionsScreenResult.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_result(self, organization_id, vendor_id, result_id) -> SanctionsScreenResult | None:
        return self.db.execute(
            select(SanctionsScreenResult).where(
                SanctionsScreenResult.id == result_id,
                SanctionsScreenResult.organization_id == organization_id,
                SanctionsScreenResult.vendor_id == vendor_id,
                SanctionsScreenResult.entity_type == "vendor",
            )
        ).scalar_one_or_none()

    def refresh_from_file(self, path: str | Path, *, target_only: bool = True, max_records: int | None = None) -> dict[str, int]:
        source_path = Path(path)
        if not source_path.exists():
            raise FileNotFoundError(f"OpenSanctions dataset file not found: {source_path}")

        processed = 0
        imported = 0
        skipped = 0
        batch: list[dict[str, Any]] = []
        with source_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if max_records is not None and processed >= max_records:
                    break
                processed += 1
                if not line.strip():
                    skipped += 1
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    skipped += 1
                    continue
                if target_only and record.get("target") is not True:
                    skipped += 1
                    continue
                row = self._row_from_ftm_record(record)
                if row is None:
                    skipped += 1
                    continue
                batch.append(row)
                if len(batch) >= 500:
                    imported += self._upsert_entities(batch)
                    batch = []
        if batch:
            imported += self._upsert_entities(batch)
        return {"records_processed": processed, "entities_imported": imported, "records_skipped": skipped}

    def download_dataset(self, *, url: str | None = None, destination: str | Path | None = None) -> Path:
        """Download a single dataset file. Kept for explicit single-URL/destination use
        (tests, custom mirrors); the daily refresh job uses download_datasets() below so
        both the OFAC SDN and consolidated lists get pulled by default."""
        dataset_url = url or os.getenv("OPEN_SANCTIONS_DATASET_URL") or OPEN_SANCTIONS_DEFAULT_URL
        destination_path = Path(destination or os.getenv("OPEN_SANCTIONS_DATASET_PATH") or DEFAULT_DATASET_PATH)
        return self._download_one(dataset_url, destination_path)

    def _download_one(self, dataset_url: str, destination_path: Path) -> Path:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False, dir=str(destination_path.parent), prefix="entities.", suffix=".tmp") as tmp:
            tmp_path = Path(tmp.name)
        try:
            # 600s: generous enough for the ~50MB OFAC SDN file even on slow/constrained
            # egress, while the switch away from the 2.7GB "default" aggregate (see the
            # comment on OPEN_SANCTIONS_DEFAULT_DATASET_URLS above) is what actually makes
            # this reliably complete rather than the timeout value itself.
            with urllib.request.urlopen(dataset_url, timeout=600) as response, tmp_path.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
            tmp_path.replace(destination_path)
            return destination_path
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def download_datasets(self) -> list[Path]:
        """Download every configured OpenSanctions dataset (OFAC SDN + consolidated by
        default; override via OPEN_SANCTIONS_DATASET_URLS, comma-separated) into distinct
        files under OPEN_SANCTIONS_DATASET_DIR / DEFAULT_DATASET_DIR."""
        explicit_single = os.getenv("OPEN_SANCTIONS_DATASET_URL")
        urls_env = os.getenv("OPEN_SANCTIONS_DATASET_URLS")
        if explicit_single:
            # A caller/deployment explicitly pinned one dataset URL -- honor it alone
            # rather than also pulling the OFAC defaults, so single-file overrides used by
            # download_dataset()/refresh_from_file() callers keep working as expected.
            urls = [explicit_single]
        elif urls_env:
            urls = [u.strip() for u in urls_env.split(",") if u.strip()]
        else:
            urls = list(OPEN_SANCTIONS_DEFAULT_DATASET_URLS)
        dataset_dir = Path(os.getenv("OPEN_SANCTIONS_DATASET_DIR") or DEFAULT_DATASET_DIR)
        paths: list[Path] = []
        for url in urls:
            slug = url.rstrip("/").split("/")[-2] if "/" in url else "dataset"
            destination_path = dataset_dir / f"{slug}.entities.ftm.json"
            paths.append(self._download_one(url, destination_path))
        return paths

    def refresh_downloaded_dataset(self) -> dict[str, int | str]:
        max_records_value = os.getenv("OPEN_SANCTIONS_REFRESH_MAX_RECORDS")
        max_records = int(max_records_value) if max_records_value and max_records_value.isdigit() else None
        dataset_paths = self.download_datasets()
        total_processed = 0
        total_imported = 0
        total_skipped = 0
        for dataset_path in dataset_paths:
            result = self.refresh_from_file(dataset_path, target_only=True, max_records=max_records)
            total_processed += result["records_processed"]
            total_imported += result["entities_imported"]
            total_skipped += result["records_skipped"]
        return {
            "records_processed": total_processed,
            "entities_imported": total_imported,
            "records_skipped": total_skipped,
            "dataset_paths": ", ".join(str(p) for p in dataset_paths),
        }

    def _watchman_search(self, name: str, *, limit: int = 10) -> WatchmanSearchResult:
        try:
            with httpx.Client(timeout=self.http_timeout_seconds) as client:
                response = client.get(f"{self.watchman_base_url}/search", params={"name": name, "limit": limit})
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return WatchmanSearchResult(available=False, matches=[], error=str(exc))
        return WatchmanSearchResult(available=True, matches=self._extract_watchman_matches(payload), error=None)

    def _extract_watchman_matches(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("results", "matches", "items", "entities"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    def _local_search(self, name: str, *, limit: int = 10) -> list[dict[str, Any]]:
        tokens = _meaningful_tokens(name)
        if not tokens:
            return []
        clauses = [SanctionsEntity.caption.ilike(f"%{token}%") for token in tokens]
        candidates = self.db.execute(select(SanctionsEntity).where(or_(*clauses)).limit(500)).scalars().all()
        matches = []
        for entity in candidates:
            score = _score_names(name, entity.caption)
            matches.append(
                {
                    "id": entity.id,
                    "caption": entity.caption,
                    "schema": entity.schema_type,
                    "score": score,
                    "datasets": entity.datasets,
                    "countries": entity.countries,
                    "properties": entity.properties,
                }
            )
        return sorted(matches, key=lambda item: item["score"], reverse=True)[:limit]

    def _normalize_match(self, match: dict[str, Any], query_name: str) -> dict[str, Any]:
        caption = (
            match.get("caption")
            or match.get("name")
            or match.get("entity_name")
            or match.get("display_name")
            or match.get("title")
            or ""
        )
        score_value = match.get("score", match.get("match", match.get("confidence")))
        try:
            score = float(score_value)
        except (TypeError, ValueError):
            score = _score_names(query_name, str(caption))
        if score > 1:
            score = score / 100
        return {
            "entity_id": str(match.get("id") or match.get("entity_id") or match.get("subject_id") or ""),
            "caption": str(caption),
            "schema": match.get("schema") or match.get("schema_type") or match.get("type"),
            "score": round(max(0.0, min(1.0, score)), 4),
            "datasets": match.get("datasets") or match.get("lists") or [],
            "countries": match.get("countries") or [],
            "properties": match.get("properties") or {},
        }

    def _row_from_ftm_record(self, record: dict[str, Any]) -> dict[str, Any] | None:
        entity_id = record.get("id")
        caption = record.get("caption")
        schema_type = record.get("schema")
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else {}
        if not entity_id or not caption or not schema_type:
            return None
        return {
            "id": str(entity_id),
            "caption": str(caption)[:1024],
            "schema_type": str(schema_type)[:100],
            "countries": _country_values(properties),
            "datasets": _as_list(record.get("datasets")),
            "last_seen": _parse_last_seen(record.get("last_seen")),
            "properties": {**properties, "target": record.get("target")},
        }

    def _upsert_entities(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        bind = self.db.get_bind()
        if bind.dialect.name == "postgresql":
            stmt = pg_insert(SanctionsEntity).values(rows)
            update_columns = {
                "caption": stmt.excluded.caption,
                "schema_type": stmt.excluded.schema_type,
                "countries": stmt.excluded.countries,
                "datasets": stmt.excluded.datasets,
                "last_seen": stmt.excluded.last_seen,
                "properties": stmt.excluded.properties,
            }
            self.db.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update_columns))
        else:
            for row in rows:
                self.db.merge(SanctionsEntity(**row))
        self.db.flush()
        return len(rows)


def screen_vendor_and_apply_effects(
    db: Session,
    organization: Organization,
    vendor: Vendor,
    *,
    actor_user_id: Any | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    audit_source: str = "tprm_intelligence_satellite",
) -> SanctionsScreenResult:
    """Screen a vendor and apply the full set of downstream effects a positive hit requires.

    A positive sanctions match must do more than just persist a record: it has to (1) be
    audited, (2) escalate the *screened vendor's own* risk tier (previously only upstream
    "nth-party" vendors were flagged via VendorSupplyChainService, leaving the actually
    sanctioned vendor's own risk_tier untouched), and (3) still propagate an nth-party
    signal to any vendors that depend on this one.
    """
    row = SanctionsScreeningService(db).screen_vendor(organization, vendor)
    audit = AuditService(db)
    audit.write_audit_log(
        action="vendor.sanctions_screen.computed",
        entity_type="sanctions_screen_result",
        entity_id=row.id,
        organization_id=organization.id,
        actor_user_id=actor_user_id,
        after_json={
            "vendor_id": str(vendor.id),
            "match_found": row.match_found,
            "top_score": (row.match_details or {}).get("top_score"),
            "source": (row.match_details or {}).get("source"),
        },
        metadata_json={"source": audit_source},
        ip_address=ip_address,
        user_agent=user_agent,
    )

    if row.match_found:
        if vendor.risk_tier != SANCTIONS_ESCALATED_RISK_TIER:
            before_tier = vendor.risk_tier
            vendor.risk_tier = SANCTIONS_ESCALATED_RISK_TIER
            # Remember the pre-escalation tier on the result itself so that clearing a
            # false-positive match (see clear_vendor_sanctions_screen) can restore it
            # instead of leaving the vendor stuck at "critical" forever.
            row.match_details = {**(row.match_details or {}), "pre_escalation_risk_tier": before_tier}
            db.flush()
            audit.write_audit_log(
                action="vendor.risk_tier_escalated",
                entity_type="vendor",
                entity_id=vendor.id,
                organization_id=organization.id,
                actor_user_id=actor_user_id,
                before_json={"risk_tier": before_tier},
                after_json={"risk_tier": SANCTIONS_ESCALATED_RISK_TIER, "reason": "sanctions_match_found"},
                metadata_json={"source": audit_source, "sanctions_screen_result_id": str(row.id)},
                ip_address=ip_address,
                user_agent=user_agent,
            )

            # The vendor's risk_tier just changed to "critical", which is one of the two
            # direct inputs (alongside active supply-chain links) to T1-6's concentration
            # HHI calculation. Without this, an org that already opted into concentration
            # monitoring would keep showing a stale HHI/status until someone happened to
            # trigger an unrelated vendor update or supply-chain link change.
            from app.services.vendor_concentration_risk_service import VendorConcentrationRiskService

            concentration_service = VendorConcentrationRiskService(db)
            existing_detection = concentration_service.current(organization.id)
            # Only recompute for organizations that have already opted into concentration
            # monitoring (a detection row already exists). This keeps the persisted HHI/
            # status current with a sanctions-driven risk_tier escalation instead of
            # silently going stale, while avoiding unnecessary work for orgs that never
            # use the feature.
            if existing_detection is not None:
                detection, risk_created, state_changed = concentration_service.recompute(
                    organization_id=organization.id,
                    actor_user_id=actor_user_id,
                    threshold_hhi_score=existing_detection.threshold_hhi_score,
                )
                if state_changed:
                    audit.write_audit_log(
                        action="vendor_concentration_risk.recomputed",
                        entity_type="vendor_concentration_risk_detection",
                        entity_id=detection.id,
                        organization_id=organization.id,
                        actor_user_id=actor_user_id,
                        after_json={
                            "status": detection.status,
                            "hhi_score": detection.hhi_score,
                            "risk_id": str(detection.risk_id) if detection.risk_id else None,
                        },
                        metadata_json={"source": "vendor.sanctions_screen.computed", "risk_created": risk_created},
                    )

        from app.services.vendor_supply_chain_service import VendorSupplyChainService

        alerts = VendorSupplyChainService(db).propagate_vendor_signal(
            organization_id=organization.id,
            triggering_vendor_id=vendor.id,
            signal_type="sanctions_match_found",
            severity="critical",
            explanation="positive sanctions screening match requires immediate first-party vendor review",
            source_entity_type="sanctions_screen_result",
            source_entity_id=row.id,
            actor_user_id=actor_user_id,
        )
        for alert in alerts:
            audit.write_audit_log(
                action="vendor_supply_chain.alert_propagated",
                entity_type="vendor_supply_chain_alert",
                entity_id=alert.id,
                organization_id=organization.id,
                actor_user_id=actor_user_id,
                after_json={
                    "parent_vendor_id": str(alert.parent_vendor_id),
                    "triggering_vendor_id": str(vendor.id),
                    "signal_type": alert.signal_type,
                    "severity": alert.severity,
                },
                metadata_json={"source": "vendor.sanctions_screen.computed"},
                ip_address=ip_address,
                user_agent=user_agent,
            )

    return row


def run_daily_sanctions_dataset_refresh(db: Session) -> dict[str, int | str]:
    return SanctionsScreeningService(db).refresh_downloaded_dataset()


def run_periodic_vendor_sanctions_rescreen_sweep(db: Session) -> dict[str, int]:
    """Re-screen active vendors on a recurring cadence.

    Sanctions screening was previously only triggered manually (e.g. at onboarding) via
    POST /vendors/{id}/sanctions-screen/compute. A vendor cleared (or never screened) at
    onboarding could be newly added to a sanctions list afterwards and this platform would
    never notice unless a human happened to re-run the check. This sweep closes that gap by
    re-screening every non-archived vendor against the (daily-refreshed) sanctions dataset.

    Each vendor is screened and committed independently so a single failure (e.g. a
    transient Watchman/network error) does not roll back progress already made for other
    vendors in the sweep.
    """
    vendor_ids = db.execute(
        select(Vendor.id).where(Vendor.status != "archived").order_by(Vendor.organization_id, Vendor.id)
    ).scalars().all()

    screened = 0
    matches_found = 0
    errors = 0
    dataset_unavailable = False
    for vendor_id in vendor_ids:
        if dataset_unavailable:
            break
        try:
            vendor = db.get(Vendor, vendor_id)
            if vendor is None:
                continue
            organization = db.get(Organization, vendor.organization_id)
            if organization is None:
                continue
            row = screen_vendor_and_apply_effects(
                db,
                organization,
                vendor,
                actor_user_id=None,
                audit_source="sanctions_rescreen_sweep",
            )
            db.commit()
            screened += 1
            if row.match_found:
                matches_found += 1
        except SanctionsDatasetUnavailable:
            db.rollback()
            dataset_unavailable = True
        except Exception:
            db.rollback()
            errors += 1

    return {
        "vendors_screened": screened,
        "positive_matches_found": matches_found,
        "errors": errors,
        "records_processed": screened,
    }
