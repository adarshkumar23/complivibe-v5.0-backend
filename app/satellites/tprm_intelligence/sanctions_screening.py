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

OPEN_SANCTIONS_DEFAULT_URL = "https://data.opensanctions.org/datasets/latest/default/entities.ftm.json"
DEFAULT_DATASET_PATH = "data/opensanctions/entities.ftm.json"
DEFAULT_WATCHMAN_BASE_URL = "http://localhost:8084"
DEFAULT_THRESHOLD = 0.85


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
        row = SanctionsScreenResult(
            organization_id=organization.id,
            vendor_id=vendor.id,
            entity_type="vendor",
            entity_id=str(vendor.id),
            list_name="opensanctions_default",
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
                "matches": normalized_matches,
            },
        )
        self.db.add(row)
        self.db.flush()
        return row

    def latest_result(self, organization_id, vendor_id) -> SanctionsScreenResult | None:
        return self.db.execute(
            select(SanctionsScreenResult)
            .where(
                SanctionsScreenResult.organization_id == organization_id,
                SanctionsScreenResult.vendor_id == vendor_id,
                SanctionsScreenResult.entity_type == "vendor",
            )
            .order_by(SanctionsScreenResult.screened_at.desc(), SanctionsScreenResult.id.desc())
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
        dataset_url = url or os.getenv("OPEN_SANCTIONS_DATASET_URL") or OPEN_SANCTIONS_DEFAULT_URL
        destination_path = Path(destination or os.getenv("OPEN_SANCTIONS_DATASET_PATH") or DEFAULT_DATASET_PATH)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False, dir=str(destination_path.parent), prefix="entities.", suffix=".tmp") as tmp:
            tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(dataset_url, timeout=120) as response, tmp_path.open("wb") as handle:
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

    def refresh_downloaded_dataset(self) -> dict[str, int | str]:
        dataset_path = self.download_dataset()
        max_records_value = os.getenv("OPEN_SANCTIONS_REFRESH_MAX_RECORDS")
        max_records = int(max_records_value) if max_records_value and max_records_value.isdigit() else None
        result = self.refresh_from_file(dataset_path, target_only=True, max_records=max_records)
        return {**result, "dataset_path": str(dataset_path)}

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


def run_daily_sanctions_dataset_refresh(db: Session) -> dict[str, int | str]:
    return SanctionsScreeningService(db).refresh_downloaded_dataset()
